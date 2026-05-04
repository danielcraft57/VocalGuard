#!/usr/bin/env python3
"""
Attentes d'état d'appel (décroché / voix / raccrochage) côté scénario.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Tuple

from loguru import logger

from labcore.voice_activity import SpeechActivityDetector, VaKind
from labcore.wav_pcm8_writer import WavPcm8MonoWriter

AnswerReason = Literal["answer_tone", "voice_activity", "remote_hangup", "timeout", "no_vrx"]
HangupReason = Literal["remote_hangup", "timeout", "unsupported", "no_vrx"]


def _buffer_has_hangup_marker(blob: bytes) -> bool:
    if not blob:
        return False
    u = blob.upper()
    return (
        b"NO CARRIER" in u
        or b"NO ANSWER" in u
        or b"NO DIALTONE" in u
        or b"NO DIAL TONE" in u
        or b"BUSY" in u
        or b"ERROR" in u
    )


def _buffer_has_answer_marker(blob: bytes) -> bool:
    if not blob:
        return False
    u = blob.upper()
    return (
        b"CONNECT" in u
        or b"VCON" in u
        or b"VOICE" in u
        or b"+CPAS: 4" in u
        or b"+CPAS: 3" in u
        or b"+CLCC:" in u
    )


def _buffer_is_unsupported_probe(blob: bytes) -> bool:
    if not blob:
        return False
    u = blob.upper()
    # Plusieurs firmwares voix retournent ERROR/CME ERROR sur +CPAS/+CLCC
    # sans que cela signifie un raccrochage.
    return b"ERROR" in u or b"+CME ERROR" in u


def _buffer_has_dle_answer_marker(blob: bytes) -> bool:
    """
    Détection décroché via événements DLE dans le flux VRX.

    D'après la doc 5637:
    - DLE + 'a' : answer tone
    - DLE + 'H' : local off-hook
    """
    if not blob:
        return False
    return (b"\x10a" in blob) or (b"\x10H" in blob)


def _buffer_has_dle_hangup_marker(blob: bytes) -> bool:
    """
    Détection fin de ligne via événements DLE dans le flux VRX.

    DLE + 'b' : souvent remonté comme tonalité occupé / busy par les modems voix.
    """
    if not blob:
        return False
    return b"\x10b" in blob


def _chunk_activity_score_u8(chunk: bytes) -> float:
    """
    Score d'activité audio simple pour PCM 8-bit unsigned.

    Certains flux voix (répondeur, codecs modem) ne déclenchent pas toujours
    le VAD métier; ce score fournit un fallback robuste basé sur l'énergie.
    """
    if not chunk:
        return 0.0
    # Distance moyenne au silence 0x80 (128).
    mad = sum(abs(b - 128) for b in chunk) / float(len(chunk))
    # Étendue instantanée pour écarter les quasi-constantes.
    span = float(max(chunk) - min(chunk))
    return (0.7 * mad) + (0.3 * span / 2.0)


def _chunk_jitter_u8(chunk: bytes) -> float:
    """
    Mesure simple de variabilité inter-échantillons.

    Les tonalités ringback sont souvent plus régulières que la parole.
    Ce critère permet de réduire les faux positifs "tonalité = voix".
    """
    if not chunk or len(chunk) < 2:
        return 0.0
    diffs = [abs(chunk[i] - chunk[i - 1]) for i in range(1, len(chunk))]
    return sum(diffs) / float(len(diffs))


def _chunk_zcr_u8(chunk: bytes) -> float:
    """Zero-Crossing Rate du signal recentré (x-128), normalisé [0..1]."""
    if not chunk or len(chunk) < 2:
        return 0.0
    prev = int(chunk[0]) - 128
    crossings = 0
    for b in chunk[1:]:
        cur = int(b) - 128
        if (prev >= 0 > cur) or (prev < 0 <= cur):
            crossings += 1
        prev = cur
    return crossings / float(len(chunk) - 1)


def _chunk_periodicity_u8(chunk: bytes, min_lag: int = 8, max_lag: int = 80) -> float:
    """
    Périodicité via autocorrélation normalisée (max des lags).
    Plus proche de 1.0 = plus tonal/périodique.
    """
    n = len(chunk)
    if n < (max_lag + 2):
        return 0.0
    x = [int(b) - 128 for b in chunk]
    energy = sum(v * v for v in x)
    if energy <= 0:
        return 0.0
    lo = max(1, min_lag)
    hi = min(max_lag, n // 2)
    if lo > hi:
        return 0.0
    best = 0.0
    for lag in range(lo, hi + 1):
        num = 0
        for i in range(lag, n):
            num += x[i] * x[i - lag]
        score = abs(num) / float(energy)
        if score > best:
            best = score
    return best


def _read_carrier_cd(modem: Any) -> bool | None:
    """
    Lit l'état de la porteuse (DCD) si exposé par pyserial.

    Retourne:
    - True  : porteuse active
    - False : porteuse inactive (souvent appel terminé)
    - None  : non disponible / indéterminé
    """
    conn = getattr(modem, "serial_connection", None)
    if conn is None:
        return None
    try:
        # pyserial expose généralement la porteuse via l'attribut cd.
        return bool(conn.cd)
    except Exception:
        return None


def _log_cd_probe(
    scope: str,
    cd_now: bool | None,
    *,
    last_logged_cd: bool | None,
    last_log_ts: float,
    heartbeat_sec: float = 1.0,
) -> tuple[bool | None, float]:
    """
    Log DCD en live: à chaque transition et périodiquement (heartbeat).

    Utile en diagnostic terrain pour savoir si COM6 expose bien la porteuse.
    """
    now = time.monotonic()
    changed = cd_now != last_logged_cd
    heartbeat_due = (now - last_log_ts) >= heartbeat_sec
    if changed or heartbeat_due:
        logger.info("{}: DCD/cd={}", scope, cd_now)
        return cd_now, now
    return last_logged_cd, last_log_ts


async def wait_answer_or_voice_activity(
    modem: Any,
    *,
    timeout_sec: float,
    already_in_voice_mode: bool = True,
    allow_voice_activity: bool = True,
    allow_energy_fallback: bool = False,
    min_voice_trigger_sec: float = 0.0,
    energy_score_min: float = 24.0,
    energy_jitter_min: float = 8.0,
    energy_score_span_min: float = 6.0,
    energy_jitter_span_min: float = 2.5,
    tone_reject_enabled: bool = False,
    tone_reject_zcr_min: float = 0.03,
    tone_reject_zcr_max: float = 0.30,
    tone_reject_periodicity_max: float = 0.90,
    post_answer_observe_sec: float = 0.0,
    capture_delay_sec: float = 0.0,
    capture_window_sec: float = 0.0,
    capture_wav_path: str | Path | None = None,
    metrics_hook: Callable[[dict[str, float | bool | str]], None] | None = None,
    vad_threshold: float = 26.0,
    vad_min_speech_ms: float = 420.0,
    vad_hangover_ms: float = 400.0,
    exit_wait_on_voice: bool = False,
    on_vrx_pcm_u8: Callable[[bytes], None] | None = None,
    vrx_hook_only_when_capturing: bool = False,
) -> tuple[bool, AnswerReason]:
    """
    Attend d'abord un éventuel signal série de décroché, sinon la 1ère activité vocale VRX.

    Retourne ``(ready, reason)`` :
    - ``(True, "answer_tone")``  si le modem expose/retourne un indice de décroché série
    - ``(True, "voice_activity")`` si le VAD voit la première parole
    - ``(False, "remote_hangup"|"timeout"|"no_vrx")`` sinon

    Si ``post_answer_observe_sec > 0``, la fonction continue de lire le flux VRX
    pendant ce délai après la première détection positive afin de collecter des
    métriques supplémentaires (diagnostic/calibration).

    Si ``capture_wav_path`` est fourni, le PCM brut du flux VRX est écrit dans un
    WAV 8 kHz mono 8-bit (même session ``AT+VRX`` que cette fonction).

    ``capture_delay_sec`` / ``capture_window_sec`` permettent de ne pousser vers
    ``metrics_hook`` / le WAV qu'entre ``delay`` et ``delay+window`` (timeline
    ``t_sec`` depuis l'ouverture VRX). Si ``capture_window_sec > 0``, la boucle
    continue jusqu'à cette fenêtre même si un décroché est détecté tôt
    (mode calibration ; ``post_answer_observe_sec`` ne raccourcit pas la session),
    **sauf** si ``exit_wait_on_voice`` est True : alors la première voix (ou autre
    déclencheur positif) termine tout de suite la fonction — utile pour enchaîner
    prompt / répondeur sans attendre la fin de fenêtre.

    ``on_vrx_pcm_u8`` : si fourni, chaque chunk PCM u8 non vide lu sur VRX est aussi
    passé à ce callback (ex. alimenter Vosk pendant l’attente pour ne pas perdre le
    message « aucun message » avant le menu SVI).

    Si ``vrx_hook_only_when_capturing`` est True, le hook n’est appelé que lorsque
    ``capturing`` est vrai (même règle que WAV / métriques audio : après
    ``capture_delay_sec`` et dans ``capture_window_sec`` si > 0). Utile pour aligner
    STT + WAV Vosk sur ``answer_metrics_probe`` avec le même ``capture_delay_sec``.
    """
    cap_delay = max(0.0, float(capture_delay_sec))
    cap_win = max(0.0, float(capture_window_sec))
    need_until = cap_delay + cap_win if cap_win > 0 else 0.0
    tmo = max(0.5, float(timeout_sec), need_until)
    calibration_hold = cap_win > 0.0
    effective_post_observe = 0.0 if calibration_hold else max(0.0, float(post_answer_observe_sec))

    wait_fn = getattr(modem, "wait_voice_outbound_answer", None)
    if callable(wait_fn):
        try:
            # Signatures backend variées: on lit uniquement le booléen initial.
            res = await wait_fn(tmo)
            got = bool(res[0]) if isinstance(res, tuple) and res else bool(res)
            if got:
                return True, "answer_tone"
        except TypeError:
            try:
                res = await wait_fn(tmo, silent_bail_sec=min(12.0, tmo))
                got = bool(res[0]) if isinstance(res, tuple) and res else bool(res)
                if got:
                    return True, "answer_tone"
            except Exception as e:
                logger.debug("wait_answer_or_voice_activity: wait_voice_outbound_answer {}", e)
        except Exception as e:
            logger.debug("wait_answer_or_voice_activity: wait_voice_outbound_answer {}", e)

    opened = await modem.start_outgoing_vrx_stream(already_in_voice_mode=already_in_voice_mode)
    if not opened:
        return False, "no_vrx"

    read_fn = getattr(modem, "read_vrx_chunk", None) or getattr(modem, "read_outgoing_vrx_chunk", None)
    if not callable(read_fn):
        await modem.end_outgoing_vrx_stream()
        return False, "no_vrx"

    hangup_fn = getattr(modem, "vrx_remote_line_end_detected", None)
    carrier_initial = _read_carrier_cd(modem)
    logger.info("wait_answer_or_voice_activity: DCD/cd initial={}", carrier_initial)
    last_logged_cd = carrier_initial
    last_log_ts = time.monotonic()
    det = SpeechActivityDetector(
        threshold=float(vad_threshold),
        min_speech_ms=float(vad_min_speech_ms),
        hangover_ms=float(vad_hangover_ms),
    )
    raw_active_ms = 0.0
    raw_trigger_ms = max(450.0, float(vad_min_speech_ms))
    last_raw_log_ts = time.monotonic()
    recent_scores: deque[float] = deque(maxlen=8)
    recent_jitters: deque[float] = deque(maxlen=8)
    t_deadline = time.monotonic() + tmo
    t_start = time.monotonic()
    post_observe = effective_post_observe
    detected: tuple[bool, AnswerReason] | None = None
    detected_at = 0.0
    tail = bytearray()
    wav_writer: Optional[WavPcm8MonoWriter] = None
    wav_out_path: Optional[Path] = Path(capture_wav_path) if capture_wav_path else None
    if wav_out_path:
        logger.info(
            "wait_answer_or_voice_activity: capture WAV prévue -> {} (delay={:.2f}s window={:.2f}s)",
            wav_out_path,
            cap_delay,
            cap_win,
        )
    capture_end = (cap_delay + cap_win) if cap_win > 0.0 else 0.0
    try:
        while time.monotonic() < t_deadline:
            # En mode calibration (fenêtre), on ne sort pas au premier trigger :
            # on tient la fenêtre complète pour capturer 20s stables.
            if (not calibration_hold) and detected is not None and (time.monotonic() - detected_at) >= post_observe:
                return detected
            if calibration_hold and capture_end > 0.0 and (time.monotonic() - t_start) >= capture_end:
                break
            chunk = await read_fn(2048)
            if callable(hangup_fn):
                try:
                    if await hangup_fn():
                        return False, "remote_hangup"
                except Exception:
                    pass
            carrier_now = _read_carrier_cd(modem)
            t_rel = time.monotonic() - t_start
            capturing = (t_rel >= cap_delay) and (cap_win <= 0.0 or t_rel < cap_delay + cap_win)
            if metrics_hook is not None and capturing:
                try:
                    metrics_hook(
                        {
                            "kind": "carrier",
                            "t_sec": t_rel,
                            "cd": -1.0 if carrier_now is None else (1.0 if carrier_now else 0.0),
                        }
                    )
                except Exception:
                    pass
            last_logged_cd, last_log_ts = _log_cd_probe(
                "wait_answer_or_voice_activity",
                carrier_now,
                last_logged_cd=last_logged_cd,
                last_log_ts=last_log_ts,
            )
            # Sur plusieurs modems USB, le passage DCD 0->1 est le meilleur signal de décroché.
            if carrier_initial is False and carrier_now is True:
                logger.info("wait_answer_or_voice_activity: montée porteuse DCD détectée")
                if calibration_hold:
                    if exit_wait_on_voice:
                        return True, "answer_tone"
                    if detected is None:
                        detected = (True, "answer_tone")
                        detected_at = time.monotonic()
                elif post_observe > 0.0:
                    if detected is None:
                        detected = (True, "answer_tone")
                        detected_at = time.monotonic()
                        logger.info(
                            "wait_answer_or_voice_activity: post-observe actif {:.1f}s après answer_tone",
                            post_observe,
                        )
                else:
                    return True, "answer_tone"
            if carrier_initial is None and carrier_now is True:
                # Cas où l'état initial n'était pas lisible au tout début.
                logger.info("wait_answer_or_voice_activity: porteuse DCD active")
                if calibration_hold:
                    if exit_wait_on_voice:
                        return True, "answer_tone"
                    if detected is None:
                        detected = (True, "answer_tone")
                        detected_at = time.monotonic()
                elif post_observe > 0.0:
                    if detected is None:
                        detected = (True, "answer_tone")
                        detected_at = time.monotonic()
                        logger.info(
                            "wait_answer_or_voice_activity: post-observe actif {:.1f}s après answer_tone",
                            post_observe,
                        )
                else:
                    return True, "answer_tone"
            if not chunk:
                await asyncio.sleep(0.02)
                continue
            if on_vrx_pcm_u8 is not None and (not vrx_hook_only_when_capturing or capturing):
                try:
                    on_vrx_pcm_u8(chunk)
                except Exception as e:
                    logger.warning("wait_answer_or_voice_activity: on_vrx_pcm_u8 hook: {}", e)
            if capturing and wav_out_path is not None:
                if wav_writer is None:
                    wav_writer = WavPcm8MonoWriter(wav_out_path)
                    logger.info("wait_answer_or_voice_activity: début écriture WAV -> {}", wav_writer.path)
                wav_writer.write_pcm_u8(chunk)
            tail.extend(chunk)
            if len(tail) > 4096:
                del tail[:-4096]
            if _buffer_has_hangup_marker(bytes(tail)):
                return False, "remote_hangup"
            if _buffer_has_dle_answer_marker(bytes(tail)):
                logger.info("wait_answer_or_voice_activity: marqueur DLE de décroché détecté")
                if calibration_hold:
                    if exit_wait_on_voice:
                        return True, "answer_tone"
                    if detected is None:
                        detected = (True, "answer_tone")
                        detected_at = time.monotonic()
                elif post_observe > 0.0:
                    if detected is None:
                        detected = (True, "answer_tone")
                        detected_at = time.monotonic()
                        logger.info(
                            "wait_answer_or_voice_activity: post-observe actif {:.1f}s après answer_tone",
                            post_observe,
                        )
                else:
                    return True, "answer_tone"
            if allow_voice_activity:
                voice_gate_open = t_rel >= max(0.0, float(min_voice_trigger_sec))
                if not voice_gate_open:
                    continue
                # Métriques brutes toujours calculées (diagnostic), fallback optionnel.
                chunk_ms = (len(chunk) / 8000.0) * 1000.0 if chunk else 0.0
                raw_score = _chunk_activity_score_u8(chunk)
                raw_jitter = _chunk_jitter_u8(chunk)
                raw_zcr = _chunk_zcr_u8(chunk)
                raw_periodicity = _chunk_periodicity_u8(chunk)
                recent_scores.append(raw_score)
                recent_jitters.append(raw_jitter)
                score_span = (max(recent_scores) - min(recent_scores)) if len(recent_scores) >= 4 else 0.0
                jitter_span = (max(recent_jitters) - min(recent_jitters)) if len(recent_jitters) >= 4 else 0.0
                if allow_energy_fallback:
                    is_voice_like = raw_score >= float(energy_score_min) and raw_jitter >= float(energy_jitter_min)
                    has_voice_variability = (
                        score_span >= float(energy_score_span_min)
                        or jitter_span >= float(energy_jitter_span_min)
                    )
                    passes_tone_reject = True
                    if tone_reject_enabled:
                        zcr_ok = float(tone_reject_zcr_min) <= raw_zcr <= float(tone_reject_zcr_max)
                        periodicity_ok = raw_periodicity <= float(tone_reject_periodicity_max)
                        passes_tone_reject = zcr_ok and periodicity_ok
                    if is_voice_like and has_voice_variability and passes_tone_reject:
                        raw_active_ms += chunk_ms
                    else:
                        raw_active_ms = max(0.0, raw_active_ms - chunk_ms)
                if metrics_hook is not None and capturing:
                    try:
                        metrics_hook(
                            {
                                "kind": "audio",
                                "t_sec": t_rel,
                                "raw_score": raw_score,
                                "raw_jitter": raw_jitter,
                                "raw_zcr": raw_zcr,
                                "raw_periodicity": raw_periodicity,
                                "score_span": score_span,
                                "jitter_span": jitter_span,
                                "active_ms": raw_active_ms,
                                "voice_gate_open": 1.0 if voice_gate_open else 0.0,
                            }
                        )
                    except Exception:
                        pass
                now = time.monotonic()
                if now - last_raw_log_ts >= 1.0:
                    logger.info(
                        "wait_answer_or_voice_activity: raw_score={:.1f} raw_jitter={:.1f} zcr={:.3f} per={:.3f} span=({:.1f},{:.1f}) active_ms={:.0f}",
                        raw_score,
                        raw_jitter,
                        raw_zcr,
                        raw_periodicity,
                        score_span,
                        jitter_span,
                        raw_active_ms,
                    )
                    last_raw_log_ts = now
                if allow_energy_fallback and raw_active_ms >= raw_trigger_ms:
                    logger.info(
                        "wait_answer_or_voice_activity: décroché par fallback énergie (score={:.1f}, jitter={:.1f})",
                        raw_score,
                        raw_jitter,
                    )
                    if calibration_hold:
                        if exit_wait_on_voice:
                            return True, "voice_activity"
                        if detected is None:
                            detected = (True, "voice_activity")
                            detected_at = time.monotonic()
                    elif post_observe > 0.0:
                        if detected is None:
                            detected = (True, "voice_activity")
                            detected_at = time.monotonic()
                            logger.info(
                                "wait_answer_or_voice_activity: post-observe actif {:.1f}s après voice_activity",
                                post_observe,
                            )
                    else:
                        return True, "voice_activity"
                for ev in det.feed(chunk):
                    if ev.kind == VaKind.SPEECH_START:
                        if calibration_hold:
                            if exit_wait_on_voice:
                                return True, "voice_activity"
                            if detected is None:
                                detected = (True, "voice_activity")
                                detected_at = time.monotonic()
                        elif post_observe > 0.0:
                            if detected is None:
                                detected = (True, "voice_activity")
                                detected_at = time.monotonic()
                                logger.info(
                                    "wait_answer_or_voice_activity: post-observe actif {:.1f}s après voice_activity",
                                    post_observe,
                                )
                        else:
                            return True, "voice_activity"
        if detected is not None:
            return detected
        return False, "timeout"
    finally:
        if wav_writer is not None:
            try:
                wav_writer.finalize()
                logger.info(
                    "wait_answer_or_voice_activity: WAV finalisé {} ({} octets PCM)",
                    wav_writer.path,
                    wav_writer.bytes_written,
                )
            except Exception as e:
                logger.warning("wait_answer_or_voice_activity: échec finalisation WAV: {}", e)
        try:
            await modem.end_outgoing_vrx_stream()
        except Exception:
            pass


async def wait_remote_hangup(
    modem: Any,
    *,
    timeout_sec: float,
    already_in_voice_mode: bool = True,
    dcd_log_heartbeat_sec: float = 18.0,
) -> tuple[bool, HangupReason]:
    """
    Attend un marqueur de fin de ligne distant (NO CARRIER/NO ANSWER/ERROR) sur VRX.

    Sur beaucoup de modems USB en sortant, ``DCD/cd`` reste à False : les logs périodiques
    sont espacés via ``dcd_log_heartbeat_sec``; un ``timeout`` est alors normal.
    """
    tmo = max(0.5, float(timeout_sec))
    hb = max(0.5, float(dcd_log_heartbeat_sec))
    try:
        opened = await modem.start_outgoing_vrx_stream(already_in_voice_mode=already_in_voice_mode)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        # Le modem peut être déjà raccroché / dans un état instable, et lever lors du CONNECT.
        logger.warning("wait_remote_hangup: ouverture VRX échouée: {}", e)
        return False, "no_vrx"
    if not opened:
        return False, "no_vrx"
    read_fn = getattr(modem, "read_vrx_chunk", None) or getattr(modem, "read_outgoing_vrx_chunk", None)
    if not callable(read_fn):
        await modem.end_outgoing_vrx_stream()
        return False, "unsupported"
    hangup_fn = getattr(modem, "vrx_remote_line_end_detected", None)
    carrier_initial = _read_carrier_cd(modem)
    logger.info(
        "wait_remote_hangup: écoute VRX {:.1f}s max (pas d'enregistrement ici) — DCD/cd initial={}",
        tmo,
        carrier_initial,
    )
    last_logged_cd = carrier_initial
    last_log_ts = time.monotonic()
    t_deadline = time.monotonic() + tmo
    tail = bytearray()
    try:
        while time.monotonic() < t_deadline:
            chunk = await read_fn(2048)
            if callable(hangup_fn):
                try:
                    if await hangup_fn():
                        return True, "remote_hangup"
                except Exception:
                    pass
            carrier_now = _read_carrier_cd(modem)
            last_logged_cd, last_log_ts = _log_cd_probe(
                "wait_remote_hangup",
                carrier_now,
                last_logged_cd=last_logged_cd,
                last_log_ts=last_log_ts,
                heartbeat_sec=hb,
            )
            # Si la porteuse était présente et retombe, on considère un raccrochage distant.
            if carrier_initial is True and carrier_now is False:
                logger.info("wait_remote_hangup: perte de porteuse DCD détectée")
                return True, "remote_hangup"
            if chunk:
                tail.extend(chunk)
                if len(tail) > 4096:
                    del tail[:-4096]
                if _buffer_has_hangup_marker(bytes(tail)):
                    return True, "remote_hangup"
            else:
                await asyncio.sleep(0.03)
        return False, "timeout"
    finally:
        try:
            await modem.end_outgoing_vrx_stream()
        except Exception:
            pass


async def wait_remote_line_end_optional(
    modem: Any,
    *,
    timeout_sec: float,
    already_in_voice_mode: bool = True,
    dcd_log_heartbeat_sec: float = 18.0,
    session_note: str = "",
) -> tuple[bool | None, HangupReason | None]:
    """
    Si ``timeout_sec`` > 0 : ouvre VRX et délègue à :func:`wait_remote_hangup`.

    Utile après une phase métriques/WAV ou après enregistrement répondeur ; aucune nouvelle
    capture fichier. Retourne ``(None, None)`` lorsque l'étape est désactivée (timeout ≤ 0).
    """
    t = float(timeout_sec)
    if t <= 0:
        return None, None
    suffix = f" {session_note.strip()}" if session_note.strip() else ""
    logger.info(
        "Étape optionnelle : écoute fin de ligne {:.1f}s (wait_remote_hangup){} — pas d'enregistrement ; timeout fréquent si DCD absent.",
        t,
        suffix,
    )
    return await wait_remote_hangup(
        modem,
        timeout_sec=t,
        already_in_voice_mode=already_in_voice_mode,
        dcd_log_heartbeat_sec=float(dcd_log_heartbeat_sec),
    )


async def probe_remote_hangup_on_active_vrx(
    modem: Any,
    *,
    chunk_tail: bytes,
    carrier_initial: bool | None,
) -> bool:
    """
    Sonde de fin de ligne distante **sans** ouvrir/fermer de VRX.

    À utiliser dans une boucle qui lit déjà le flux VRX (ex: pump STT live).
    Réutilise la même logique que ``wait_remote_hangup`` :
    - signal modem ``vrx_remote_line_end_detected`` si dispo
    - transition DCD True -> False
    - marqueurs texte ``NO CARRIER`` / ``NO ANSWER`` dans le flux
    """
    hangup_fn = getattr(modem, "vrx_remote_line_end_detected", None)
    if callable(hangup_fn):
        try:
            if await hangup_fn():
                return True
        except Exception:
            pass

    carrier_now = _read_carrier_cd(modem)
    if carrier_initial is True and carrier_now is False:
        return True

    if _buffer_has_hangup_marker(chunk_tail):
        return True

    if _buffer_has_dle_hangup_marker(chunk_tail):
        return True

    return False

