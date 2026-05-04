#!/usr/bin/env python3
"""Lecture WAV vers la ligne téléphonique (mode voix série), réutilisable."""

import tempfile
import wave
from pathlib import Path
from typing import Optional

from loguru import logger


async def play_wav_line_fallback(
    modem,
    wav_path: Path,
    *,
    prefer_already_in_voice: bool = False,
    pcm_u8: Optional[bytes] = None,
    pcm_rate: Optional[float] = None,
) -> bool:
    """
    Joue un WAV 8 kHz sur la ligne avec deux stratégies.

    Par défaut (appel entrant / composition aveugle) : séquence voix complète d'abord
    (souvent plus fiable sur USB), puis repli « déjà en voix ».

    prefer_already_in_voice=True (appel sortant après CONNECT) : tenter d'abord sans
    FCLASS/VLS — renvoyer toute la séquence sur une ligne déjà établie provoque souvent
    des tonalités aiguës et pas de PCM audible.

    Les backends ``ModemHandler`` classiques n'acceptent que ``wav_path`` et
    ``already_in_voice_mode`` : on n'envoie ``pcm_u8`` / ``pcm_rate`` que si un buffer
    est fourni, avec repli fichier temporaire si le modem ne les supporte pas.
    """
    if not wav_path.is_file():
        logger.error("WAV introuvable: {}", wav_path)
        return False

    async def _play_once(already_in_voice_mode: bool) -> bool:
        if pcm_u8 is not None:
            rate = float(pcm_rate) if pcm_rate is not None else 8000.0
            try:
                return await modem.play_wav_via_serial(
                    wav_path,
                    already_in_voice_mode=already_in_voice_mode,
                    pcm_u8=pcm_u8,
                    pcm_rate=rate,
                )
            except TypeError:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                try:
                    _write_u8_wav_minimal(tmp_path, pcm_u8, int(rate))
                    return await modem.play_wav_via_serial(
                        tmp_path,
                        already_in_voice_mode=already_in_voice_mode,
                    )
                finally:
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
        return await modem.play_wav_via_serial(
            wav_path,
            already_in_voice_mode=already_in_voice_mode,
        )

    first, second = (True, False) if prefer_already_in_voice else (False, True)
    ok = await _play_once(first)
    if ok:
        return True
    logger.warning(
        "Lecture WAV (already_in_voice_mode={}) KO, retry avec already_in_voice_mode={}",
        first,
        second,
    )
    return await _play_once(second)


def wav_file_to_mono_u8_pcm(wav_path: Path) -> bytes:
    """
    Lit un WAV et renvoie le PCM mono 8-bit non signé (0–255), comme pour AT+VTX.

    Précondition habituelle : 8 kHz mono ; autres formats sont convertis grossièrement.
    """
    with wave.open(str(wav_path), "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    if rate != 8000:
        logger.warning("wav_file_to_mono_u8_pcm: {} Hz — le modem attend en général 8000 Hz", rate)
    if sw == 1:
        if nch <= 1:
            return frames
        return bytes(frames[i] for i in range(0, len(frames), nch))
    if sw == 2:
        out = bytearray()
        stride = 2 * max(1, nch)
        for i in range(0, len(frames), stride):
            sample = int.from_bytes(frames[i : i + 2], "little", signed=True)
            out.append(max(0, min(255, (sample >> 8) + 128)))
        return bytes(out)
    logger.warning("wav_file_to_mono_u8_pcm: largeur d'échantillon {} non supportée", sw)
    return b""


async def play_wav_via_half_duplex_uplink(modem, wav_path: Path) -> bool:
    """
    Envoie le contenu audio via ``half_duplex_send_uplink_u8`` (ferme VRX, VTX, rouvre VRX).

    À utiliser après une session ``AT+VRX`` streaming pour éviter un VTX « muet » sur certains chipsets.
    """
    fn = getattr(modem, "half_duplex_send_uplink_u8", None)
    if not callable(fn):
        return False
    pcm = wav_file_to_mono_u8_pcm(wav_path)
    if not pcm:
        return False
    try:
        ok = await fn(pcm)
    except Exception as e:
        logger.warning("half_duplex_send_uplink_u8: {}", e)
        return False
    if ok:
        logger.debug("half_duplex uplink OK ({} octets PCM)", len(pcm))
    return bool(ok)


def _write_u8_wav_minimal(path: Path, raw_u8: bytes, rate: int = 8000) -> None:
    """WAV mono u8 minimal (même convention que ``line_audio_player``)."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(rate)
        wf.writeframes(raw_u8)


async def record_wav_line_fallback(
    modem,
    duration_sec: float,
    out_path: Path,
    *,
    prefer_already_in_voice: bool = False,
    stop_on_remote_hangup: bool = True,
) -> bool:
    """Enregistrement ligne (VRX) avec le même ordre de repli que play_wav_line_fallback."""
    async def _record_once(already_in_voice_mode: bool) -> bool:
        try:
            return await modem.record_wav_via_serial(
                duration_sec,
                out_path,
                already_in_voice_mode=already_in_voice_mode,
                stop_on_remote_hangup=stop_on_remote_hangup,
            )
        except TypeError:
            # Backends legacy: pas de stop_on_remote_hangup.
            try:
                return await modem.record_wav_via_serial(
                    duration_sec,
                    out_path,
                    already_in_voice_mode=already_in_voice_mode,
                )
            except TypeError:
                # Backends plus anciens: seulement (duration, path).
                return await modem.record_wav_via_serial(duration_sec, out_path)

    first, second = (True, False) if prefer_already_in_voice else (False, True)
    ok = await _record_once(first)
    if ok:
        return True
    logger.warning(
        "Enregistrement WAV (already_in_voice_mode={}) KO, retry avec already_in_voice_mode={}",
        first,
        second,
    )
    return await _record_once(second)
