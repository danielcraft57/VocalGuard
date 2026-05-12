#!/usr/bin/env python3
"""
Conversation locale micro <-> casque sur PC, sans modem ni appel.

Mode enrichi:
- son d'ouverture (bip ou WAV ; avec --prospection-pack : salutation du pack depuis les JSON intents)
- reponses intents prospection sans ML (chaine CSV / preset DanielCraft outbound : premier motif matche dans la transcription puis WAV aleatoire)
- barge-in : pause de la lecture (file intents) au micro ou sur partial Vosk
- relais micro -> casque en direct
- Vosk live (PARTIAL/FINAL) + export transcript.srt
"""

from __future__ import annotations

import argparse
import atexit
import math
import queue
import random
import shutil
import sys
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

_MODEM_LAB_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_MODEM_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODEM_LAB_ROOT))

from labcore.bootstrap import setup_logging
from labcore.keyword_intent_trigger import KeywordIntentTrigger, KeywordTrigger
from labcore.pc_prospection_local import (
    DEFAULT_DANIELCRAFT_OUTBOUND_REL_CHAIN,
    match_intent_tag,
    merge_intent_chain_rows,
    pick_random_variant_wav,
    resolve_chain_paths,
)
from labcore.prospection_dialogue.opening import (
    infer_opening_tag_from_intent_json_paths,
    pick_opening_wav_from_pack,
)
from labaudio.vosk_lab import (
    DEFAULT_PROFILE_PATH,
    FRENCH_MODELS,
    print_models_catalog,
    resolve_vosk_model_dir,
    run_configure_only_flow,
)
from labaudio.vosk_stt import (
    VoskRealtimeWorker,
    format_timestamp_sub,
    offset_timed_utterances,
    preload_vosk_model,
    write_subrip,
)


RATE = 16000
CHANNELS = 1
FRAMES_PER_BUFFER = 320  # 20 ms @ 16 kHz


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Conversation micro/casque locale (sans modem): ouverture audio, relais live, "
            "transcription Vosk temps reel."
        ),
    )
    p.add_argument("--input-device", type=int, default=None, help="Index peripherique micro (vide=defaut)")
    p.add_argument("--output-device", type=int, default=None, help="Index peripherique casque (vide=defaut)")
    p.add_argument(
        "--duration-sec",
        type=float,
        default=0.0,
        help="Duree max (s). 0 = jusqu'a Ctrl+C",
    )
    p.add_argument("--opening-beep-ms", type=int, default=350, help="Duree du bip d'ouverture (ms)")
    p.add_argument("--opening-beep-hz", type=float, default=660.0, help="Frequence du bip d'ouverture (Hz)")
    p.add_argument(
        "--opening-wav",
        type=Path,
        default=None,
        help="WAV d'ouverture (PCM16 mono 16 kHz recommande). Si absent: bip synthetique.",
    )
    p.add_argument(
        "--opening-tail-silence-ms",
        type=int,
        default=120,
        help="Silence apres bip, avant debut du relais micro (ms)",
    )
    p.add_argument(
        "--monitor",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Si actif: renvoie le micro vers le casque (sidetone logiciel). Defaut: non.",
    )
    p.add_argument(
        "--push-to-talk",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Micro coupe par defaut ; parler en maintenant la touche choisie.",
    )
    p.add_argument(
        "--ptt-key",
        type=str,
        default="space",
        help="Touche push-to-talk (defaut: space).",
    )
    p.add_argument("--print-partials", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--subtitle-flush-sec", type=float, default=0.7, help="Intervalle de reecriture transcript.srt")
    p.add_argument(
        "--subtitle-out",
        type=Path,
        default=Path("scripts/modem_lab/generated/pc_headset_direct/transcript.srt"),
        help="Sortie sous-titres SRT",
    )
    p.add_argument("--dated-outfiles", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--vosk-model", type=Path, default=None, help="Repertoire modele Vosk (prioritaire)")
    p.add_argument("--vosk-model-slug", choices=sorted(FRENCH_MODELS.keys()), default=None)
    p.add_argument("--vosk-profile", type=Path, default=DEFAULT_PROFILE_PATH)
    p.add_argument("--vosk-cache-dir", type=Path, default=None)
    p.add_argument("--vosk-save-profile", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--vosk-interactive", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument(
        "--preload-vosk-model",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Precharge le modele Vosk avant demarrage audio.",
    )
    p.add_argument("--vosk-list-models", action="store_true")
    p.add_argument(
        "--vosk-download-all-fr",
        action="store_true",
        help="Telecharge tous les modeles FR du catalogue puis quitte.",
    )
    p.add_argument("--vosk-configure-only", action="store_true")
    p.add_argument(
        "--allo-trigger",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Detecte 'allo' dans les phrases finales Vosk.",
    )
    p.add_argument(
        "--allo-intent-wav",
        type=Path,
        default=None,
        help="WAV a jouer quand 'allo' est detecte (PCM16 mono 16 kHz recommande).",
    )
    p.add_argument(
        "--prospection-pack",
        type=Path,
        default=None,
        help="Repertoire des WAV intents (PCM16 mono 16 kHz, {tag}_NN.wav). Combiner avec --prospection-chain-preset ou repeter --prospection-intents-json.",
    )
    p.add_argument(
        "--prospection-intents-json",
        action="append",
        default=None,
        help="JSON d’intents (chemin repo relatif, repetable). Sinon --prospection-chain-preset=danielcraft-outbound.",
    )
    p.add_argument(
        "--prospection-chain-preset",
        choices=("none", "danielcraft-outbound"),
        default="none",
        help="Preset de liste de JSON métier DanielCraft outbound (sans passer --prospection-intents-json plusieurs fois).",
    )
    p.add_argument(
        "--prospection-seed",
        type=int,
        default=None,
        help="Graine RNG pour tirage WAV (ouverture + variantes intents). Vide = non deterministe.",
    )
    p.add_argument(
        "--prospection-open-with-beep",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Avec --prospection-pack: court bip avant la salutation pack (sinon WAV seul).",
    )
    p.add_argument(
        "--barge-in",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pause la lecture en file (intent) lorsque du signal micro fort est detecté (conversation fluide).",
    )
    p.add_argument(
        "--barge-in-on-vosk-partial",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Si actif: vide la lecture des que Vosk emet un partial avec au moins 2 caracteres.",
    )
    p.add_argument("--barge-in-rms-threshold", type=float, default=920.0, help="Seuil RMS PCM16 (~0-32767)")
    p.add_argument(
        "--barge-in-speech-ms",
        type=float,
        default=50.0,
        help="Duree min de signal au-dessus du seuil pour considerer comme parole (interrupt).",
    )
    p.add_argument(
        "--barge-in-hangover-ms",
        type=float,
        default=120.0,
        help="Temps sous le seuil avant de relacher l’état parole (pour ne pas doubler trop de clears).",
    )
    p.add_argument(
        "--list-devices",
        action="store_true",
        help="Affiche les peripheriques audio detectes puis quitte",
    )
    return p.parse_args()


def _beep_pcm16(duration_ms: int, freq_hz: float) -> bytes:
    n = max(1, int(RATE * max(0, duration_ms) / 1000.0))
    amp = 0.22
    fade_len = max(1, int(0.008 * RATE))
    data = bytearray(n * 2)
    for i in range(n):
        env = 1.0
        if i < fade_len:
            env = i / fade_len
        elif i >= n - fade_len:
            env = max(0.0, (n - i) / fade_len)
        s = int(32767.0 * amp * env * math.sin(2.0 * math.pi * freq_hz * (i / RATE)))
        j = i * 2
        data[j] = s & 0xFF
        data[j + 1] = (s >> 8) & 0xFF
    return bytes(data)


def _terminal_columns() -> int:
    try:
        return max(48, shutil.get_terminal_size((100, 20)).columns)
    except OSError:
        return 100


def _one_line_display(s: str) -> str:
    return " ".join((s or "").replace("\n", " ").replace("\r", " ").split())


def _read_opening_wav_pcm16(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wf:
        n_ch = int(wf.getnchannels())
        sw = int(wf.getsampwidth())
        fr = int(wf.getframerate())
        n_frames = int(wf.getnframes())
        raw = wf.readframes(n_frames)
    if sw != 2:
        raise ValueError(f"WAV ouverture non supporte (sample width={sw}, attendu 16-bit).")
    if fr != RATE:
        raise ValueError(f"WAV ouverture non supporte (rate={fr}, attendu {RATE}).")
    if n_ch == 1:
        return raw
    if n_ch == 2:
        out = bytearray(len(raw) // 2)
        j = 0
        for i in range(0, len(raw), 4):
            l = int.from_bytes(raw[i : i + 2], "little", signed=True)
            r = int.from_bytes(raw[i + 2 : i + 4], "little", signed=True)
            m = (l + r) // 2
            out[j] = m & 0xFF
            out[j + 1] = (m >> 8) & 0xFF
            j += 2
        return bytes(out)
    raise ValueError(f"WAV ouverture non supporte (channels={n_ch}, attendu mono/stereo).")


def _read_wav_pcm16_mono_16k(path: Path) -> bytes:
    """Lit un WAV PCM16 mono/stereo 16kHz et retourne PCM16 mono."""
    return _read_opening_wav_pcm16(path)


def _build_opening_pcm16(args: argparse.Namespace) -> bytes:
    if args.opening_wav is not None:
        return _read_opening_wav_pcm16(Path(args.opening_wav))
    beep = _beep_pcm16(args.opening_beep_ms, args.opening_beep_hz)
    tail_silence = b"\x00\x00" * int((RATE * max(0, args.opening_tail_silence_ms)) / 1000.0)
    return beep + tail_silence


def _build_opening_with_prospection_pack(
    args: argparse.Namespace,
    *,
    pack_dir: Path,
    chain_json_paths: list[Path],
    rng: random.Random,
) -> bytes:
    """Salutation initiale depuis le pack (tag déduit des JSON) + silence de queue."""
    if args.opening_wav is not None:
        return _build_opening_pcm16(args)
    parts: list[bytes] = []
    if bool(args.prospection_open_with_beep):
        parts.append(_beep_pcm16(args.opening_beep_ms, args.opening_beep_hz))
    tag = infer_opening_tag_from_intent_json_paths(tuple(chain_json_paths))
    if tag:
        op = pick_opening_wav_from_pack(pack_dir, tag, rng)
        if op is not None and op.is_file():
            try:
                parts.append(_read_opening_wav_pcm16(op))
            except Exception as e:
                logger.warning("WAV salutation pack illisible ({}), fallback bip: {}", op, e)
    if not parts:
        return _build_opening_pcm16(args)
    tail_silence = b"\x00\x00" * int((RATE * max(0, args.opening_tail_silence_ms)) / 1000.0)
    return b"".join(parts) + tail_silence


def _apply_new_final_utterances(
    uts: list,
    start_idx: int,
    *,
    playback: _PlaybackQueue,
    args: argparse.Namespace,
    rng: random.Random,
    prospection_pack: Path | None,
    prospection_rows: list[tuple[str, list[str]]] | None,
    trigger: KeywordIntentTrigger | None,
) -> int:
    if len(uts) <= start_idx:
        return start_idx
    cols = _terminal_columns()
    for u in uts[start_idx:]:
        body = _one_line_display(u.text).strip()
        head = f"[FINAL {format_timestamp_sub(u.start_sec)} -> {format_timestamp_sub(u.end_sec)}] "
        room = max(24, cols - len(head) - 1)
        bshow = body
        if len(bshow) > room:
            bshow = bshow[: max(room - 3, 1)] + "..."
        print(head + bshow, flush=True)
        matched = False
        if prospection_pack is not None and prospection_rows:
            tag_hit = match_intent_tag(body, prospection_rows)
            if tag_hit:
                wp = pick_random_variant_wav(prospection_pack, tag_hit, rng)
                if wp is not None:
                    try:
                        playback.enqueue_pcm16(_read_wav_pcm16_mono_16k(wp))
                        logger.info("Prospection '{}' -> {}", tag_hit, wp.name)
                        matched = True
                    except Exception as e:
                        logger.warning("Lecture WAV prospection: {}", e)
        if not matched and trigger is not None:
            for tag in trigger.consider_final(u.text):
                if tag == "allo" and args.allo_intent_wav:
                    try:
                        wav = _read_wav_pcm16_mono_16k(Path(args.allo_intent_wav))
                        playback.enqueue_pcm16(wav)
                        logger.info("Trigger '{}' detecte -> lecture intent {}", tag, args.allo_intent_wav)
                    except Exception as e:
                        logger.warning("Lecture intent allo echouee: {}", e)
    return len(uts)


class _PlaybackQueue:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buf = bytearray()

    def enqueue_pcm16(self, pcm16: bytes) -> None:
        if not pcm16:
            return
        with self._lock:
            self._buf.extend(pcm16)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    def pop(self, n_bytes: int) -> bytes:
        if n_bytes <= 0:
            return b""
        with self._lock:
            if not self._buf:
                return b""
            take = min(n_bytes, len(self._buf))
            out = bytes(self._buf[:take])
            del self._buf[:take]
            return out


class _MicBargeInDetector:
    """
    Détection simple d’entrée parole (micro) par RMS PCM16 avec hystérésis pour
    déclencher **une fois** au début d’une parole (rising edge vers « parole » activée).
    """

    __slots__ = (
        "_above_ms",
        "_below_ms",
        "_rms_threshold",
        "_min_above_ms",
        "_hangover_ms",
        "_rate",
        "_speech",
    )

    def __init__(
        self,
        *,
        rms_threshold: float,
        speech_ms: float,
        hangover_ms: float,
        sample_rate: int = RATE,
    ) -> None:
        self._rms_threshold = float(rms_threshold)
        self._min_above_ms = max(5.0, float(speech_ms))
        self._hangover_ms = max(5.0, float(hangover_ms))
        self._rate = int(sample_rate)
        self._above_ms = 0.0
        self._below_ms = 0.0
        self._speech = False

    def feed(self, pcm16: bytes) -> bool:
        """
        Consomme un bloc PCM16. Retourne True si nouveau début de parole utilisateur détecté
        (pour vider la file de lecture intents).
        """
        n_samples = len(pcm16) // 2
        if n_samples <= 0:
            return False
        chunk_ms = 1000.0 * float(n_samples) / float(max(1, self._rate))
        ssum = 0.0
        for i in range(0, len(pcm16), 2):
            v = int.from_bytes(pcm16[i : i + 2], "little", signed=True)
            ssum += float(v) * float(v)
        rms = (ssum / float(max(1, n_samples))) ** 0.5
        loud = rms >= self._rms_threshold
        prev_intrusion = False
        if loud:
            self._above_ms += chunk_ms
            self._below_ms = 0.0
            if self._above_ms >= self._min_above_ms and not self._speech:
                self._speech = True
                prev_intrusion = True
        else:
            self._above_ms = 0.0
            self._below_ms += chunk_ms
            if self._speech and self._below_ms >= self._hangover_ms:
                self._speech = False
        return prev_intrusion


def _resolve_vosk_worker(
    args: argparse.Namespace,
    *,
    last_partial: dict[str, str],
    partial_hook: Callable[[str], None] | None = None,
) -> tuple[VoskRealtimeWorker, Path]:
    if bool(args.vosk_list_models):
        print_models_catalog()
        raise SystemExit(0)
    if bool(args.vosk_configure_only):
        rc = run_configure_only_flow(
            profile_path=Path(args.vosk_profile),
            cache_root=Path(args.vosk_cache_dir) if args.vosk_cache_dir else None,
            model_slug=args.vosk_model_slug,
            interactive=bool(args.vosk_interactive),
            list_only=False,
        )
        raise SystemExit(rc)

    model_dir, vosk_slug = resolve_vosk_model_dir(
        explicit_path=Path(args.vosk_model) if args.vosk_model else None,
        model_slug=args.vosk_model_slug,
        profile_path=Path(args.vosk_profile),
        cache_root=Path(args.vosk_cache_dir) if args.vosk_cache_dir else None,
        env_path=None,
        interactive=bool(args.vosk_interactive),
        save_profile_flag=bool(args.vosk_save_profile),
    )
    if model_dir is None:
        raise RuntimeError(
            "Modele Vosk introuvable. Utilisez --vosk-model-slug, --vosk-model ou --vosk-configure-only."
        )

    preloaded_model = None
    if bool(args.preload_vosk_model):
        try:
            logger.info("Prechargement modele Vosk: {}", model_dir)
            t0 = time.monotonic()
            preloaded_model = preload_vosk_model(model_dir, quiet=True)
            logger.info("Modele Vosk precharge en {:.1f}s", time.monotonic() - t0)
        except Exception as e:
            logger.warning("Prechargement Vosk echoue (fallback thread): {}", e)
            preloaded_model = None

    def _on_partial(t: str) -> None:
        if partial_hook is not None:
            partial_hook(t)
        if bool(args.print_partials):
            last_partial["t"] = t

    worker = VoskRealtimeWorker(
        Path(model_dir),
        sample_rate=RATE,
        on_partial=_on_partial,
        preloaded_model=preloaded_model,
    )
    worker._pc_last_partial_ref = last_partial  # type: ignore[attr-defined]
    worker._pc_slug = vosk_slug or ""  # type: ignore[attr-defined]
    return worker, Path(model_dir)


class _SubtitleFlusher:
    def __init__(self, worker: VoskRealtimeWorker, out_srt: Path, flush_sec: float) -> None:
        self._worker = worker
        self._out = out_srt
        self._flush_sec = max(0.15, float(flush_sec))
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="pc-subtitle-flush", daemon=True)
        self._last_n = -1

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3.0)
        self._flush_once()

    def _flush_once(self) -> None:
        uts = self._worker.snapshot_utterances()
        if len(uts) != self._last_n and uts:
            write_subrip(self._out, offset_timed_utterances(uts, 0.0))
            self._last_n = len(uts)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._flush_once()
            time.sleep(self._flush_sec)


class _PushToTalkController:
    def __init__(self, enabled: bool, key_name: str) -> None:
        self.enabled = bool(enabled)
        self.key_name = (key_name or "space").strip().lower()
        self.tx_enabled = not self.enabled
        self._listener = None
        self._ready = False

    def start(self) -> None:
        if not self.enabled:
            self.tx_enabled = True
            return
        try:
            from pynput import keyboard
        except Exception as e:
            raise RuntimeError(
                "Mode push-to-talk indisponible: installer 'pynput' (pip install pynput)."
            ) from e

        def _is_target(k) -> bool:
            try:
                if hasattr(k, "char") and k.char:
                    return str(k.char).lower() == self.key_name
            except Exception:
                pass
            key_attr = str(getattr(k, "name", "") or "").lower()
            if key_attr:
                return key_attr == self.key_name
            key_s = str(k).lower()
            aliases = {
                "space": ("key.space", "<96>", " "),
                "ctrl": ("key.ctrl", "key.ctrl_l", "key.ctrl_r"),
                "alt": ("key.alt", "key.alt_l", "key.alt_r"),
                "shift": ("key.shift", "key.shift_l", "key.shift_r"),
            }
            if self.key_name in aliases:
                return any(a in key_s for a in aliases[self.key_name])
            return self.key_name in key_s

        def _on_press(k) -> None:
            if _is_target(k):
                self.tx_enabled = True

        def _on_release(k) -> None:
            if _is_target(k):
                self.tx_enabled = False

        self._listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
        self._listener.start()
        self._ready = True

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self._ready = False


def _list_devices() -> int:
    printed = False
    try:
        import sounddevice as sd

        devs = sd.query_devices()
        print("=== Peripheriques audio (sounddevice) ===")
        for idx, d in enumerate(devs):
            print(f"[{idx}] {d.get('name', '?')} | in={d.get('max_input_channels', 0)} out={d.get('max_output_channels', 0)}")
        printed = True
    except Exception:
        pass

    try:
        import pyaudio

        pa = pyaudio.PyAudio()
        print("=== Peripheriques audio (pyaudio) ===")
        for idx in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(idx)
            print(f"[{idx}] {d.get('name', '?')} | in={int(d.get('maxInputChannels', 0))} out={int(d.get('maxOutputChannels', 0))}")
        pa.terminate()
        printed = True
    except Exception:
        pass

    if not printed:
        print("Aucun backend audio disponible (installer sounddevice ou pyaudio).", file=sys.stderr)
        return 2
    return 0


def _run_with_sounddevice(
    args: argparse.Namespace,
    *,
    worker: VoskRealtimeWorker,
    opening: bytes,
    ptt: _PushToTalkController,
    playback: _PlaybackQueue,
    trigger: KeywordIntentTrigger | None,
    rng: random.Random,
    prospection_pack: Path | None,
    prospection_rows: list[tuple[str, list[str]]] | None,
    barge_detector: _MicBargeInDetector | None,
) -> int:
    import sounddevice as sd

    stop_event = threading.Event()
    opening_cursor = 0
    last_mic_chunk: dict[str, bytes] = {"b": b""}

    def in_cb(indata, frames, _time_info, status):
        if status:
            logger.debug("Input status: {}", status)
        if stop_event.is_set():
            return
        if not ptt.tx_enabled:
            return
        try:
            data = bytes(indata)
            last_mic_chunk["b"] = data
            if barge_detector is not None:
                intrusion = barge_detector.feed(data)
                if intrusion:
                    playback.clear()
            _ = worker.push_pcm16_nowait(data, drop_oldest_on_full=True)
        except queue.Full:
            pass

    def out_cb(outdata, frames, _time_info, status):
        nonlocal opening_cursor
        if status:
            logger.debug("Output status: {}", status)
        need = frames * 2
        if opening_cursor < len(opening):
            chunk = opening[opening_cursor : opening_cursor + need]
            opening_cursor += len(chunk)
            if len(chunk) < need:
                chunk += b"\x00" * (need - len(chunk))
            outdata[:] = chunk
            return
        # 1) playback intents (prioritaire)
        chunk = playback.pop(need)
        if chunk:
            if len(chunk) < need:
                chunk += b"\x00" * (need - len(chunk))
            outdata[:] = chunk
            return
        # 2) monitoring micro optionnel
        if bool(args.monitor) and ptt.tx_enabled:
            mic = last_mic_chunk.get("b") or b""
            if len(mic) < need:
                mic = mic + (b"\x00" * (need - len(mic)))
            elif len(mic) > need:
                mic = mic[:need]
            outdata[:] = mic
            return
        outdata[:] = b"\x00" * need

    with sd.RawInputStream(
        samplerate=RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=FRAMES_PER_BUFFER,
        device=args.input_device,
        callback=in_cb,
    ), sd.RawOutputStream(
        samplerate=RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=FRAMES_PER_BUFFER,
        device=args.output_device,
        callback=out_cb,
    ):
        logger.info("Backend audio: sounddevice")
        if args.opening_wav:
            logger.info("Ouverture: WAV {}", args.opening_wav)
        else:
            logger.info("Ouverture: bip {} ms a {} Hz", int(args.opening_beep_ms), float(args.opening_beep_hz))
        logger.info("Vosk live actif (modele: {})", str(getattr(worker, "_pc_slug", "") or "custom/path"))
        if ptt.enabled:
            logger.info("Push-to-talk actif: maintenir '{}' pour parler.", ptt.key_name)
        if not bool(args.monitor):
            logger.info("Monitoring local: desactive (pas de retour casque).")
        print("\n>>> Conversation locale + STT active. Parlez dans le micro (Ctrl+C pour arreter).\n", flush=True)
        t0 = time.monotonic()
        last_final_idx = 0
        last_partial_printed = ""
        last_partial = getattr(worker, "_pc_last_partial_ref", {"t": ""})
        while True:
            if args.duration_sec > 0 and (time.monotonic() - t0) >= args.duration_sec:
                break
            uts = worker.snapshot_utterances()
            if len(uts) > last_final_idx:
                last_final_idx = _apply_new_final_utterances(
                    uts,
                    last_final_idx,
                    playback=playback,
                    args=args,
                    rng=rng,
                    prospection_pack=prospection_pack,
                    prospection_rows=prospection_rows,
                    trigger=trigger,
                )
            p = (last_partial.get("t") or "").strip()
            if p and p != last_partial_printed:
                cols = _terminal_columns()
                prefix = f"[PARTIAL {format_timestamp_sub(max(0.0, time.monotonic() - t0))}] "
                body = _one_line_display(p)
                room = max(16, cols - len(prefix) - 1)
                if len(body) > room:
                    body = body[: max(room - 3, 1)] + "..."
                sys.stdout.write("\r" + " " * (cols - 1) + "\r" + prefix + body)
                sys.stdout.flush()
                last_partial_printed = p
                last_partial["t"] = ""
            time.sleep(0.12)
    stop_event.set()
    try:
        sys.stdout.write("\n")
        sys.stdout.flush()
    except Exception:
        pass
    return 0


def _run_with_pyaudio(
    args: argparse.Namespace,
    *,
    worker: VoskRealtimeWorker,
    opening: bytes,
    ptt: _PushToTalkController,
    playback: _PlaybackQueue,
    trigger: KeywordIntentTrigger | None,
    rng: random.Random,
    prospection_pack: Path | None,
    prospection_rows: list[tuple[str, list[str]]] | None,
    barge_detector: _MicBargeInDetector | None,
) -> int:
    import pyaudio

    pa = pyaudio.PyAudio()
    stream_in = None
    stream_out = None
    try:
        stream_in = pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=args.input_device,
            frames_per_buffer=FRAMES_PER_BUFFER,
        )
        stream_out = pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            output_device_index=args.output_device,
            frames_per_buffer=FRAMES_PER_BUFFER,
        )
        if opening:
            stream_out.write(opening)

        logger.info("Backend audio: pyaudio")
        if args.opening_wav:
            logger.info("Ouverture: WAV {}", args.opening_wav)
        else:
            logger.info("Ouverture: bip {} ms a {} Hz", int(args.opening_beep_ms), float(args.opening_beep_hz))
        logger.info("Vosk live actif (modele: {})", str(getattr(worker, "_pc_slug", "") or "custom/path"))
        if ptt.enabled:
            logger.info("Push-to-talk actif: maintenir '{}' pour parler.", ptt.key_name)
        if not bool(args.monitor):
            logger.info("Monitoring local: desactive (pas de retour casque).")
        print("\n>>> Conversation locale + STT active. Parlez dans le micro (Ctrl+C pour arreter).\n", flush=True)
        t0 = time.monotonic()
        last_final_idx = 0
        last_partial_printed = ""
        last_partial = getattr(worker, "_pc_last_partial_ref", {"t": ""})
        while True:
            if args.duration_sec > 0 and (time.monotonic() - t0) >= args.duration_sec:
                break
            data = stream_in.read(FRAMES_PER_BUFFER, exception_on_overflow=False)
            if ptt.tx_enabled:
                if barge_detector is not None:
                    if barge_detector.feed(data):
                        playback.clear()
                _ = worker.push_pcm16_nowait(data, drop_oldest_on_full=True)
                if bool(args.monitor):
                    stream_out.write(data)
            # playback intents
            pb = playback.pop(FRAMES_PER_BUFFER * 2)
            if pb:
                if len(pb) < FRAMES_PER_BUFFER * 2:
                    pb += b"\x00" * ((FRAMES_PER_BUFFER * 2) - len(pb))
                stream_out.write(pb)
            uts = worker.snapshot_utterances()
            if len(uts) > last_final_idx:
                last_final_idx = _apply_new_final_utterances(
                    uts,
                    last_final_idx,
                    playback=playback,
                    args=args,
                    rng=rng,
                    prospection_pack=prospection_pack,
                    prospection_rows=prospection_rows,
                    trigger=trigger,
                )
            p = (last_partial.get("t") or "").strip()
            if p and p != last_partial_printed:
                cols = _terminal_columns()
                prefix = f"[PARTIAL {format_timestamp_sub(max(0.0, time.monotonic() - t0))}] "
                body = _one_line_display(p)
                room = max(16, cols - len(prefix) - 1)
                if len(body) > room:
                    body = body[: max(room - 3, 1)] + "..."
                sys.stdout.write("\r" + " " * (cols - 1) + "\r" + prefix + body)
                sys.stdout.flush()
                last_partial_printed = p
                last_partial["t"] = ""
            time.sleep(0.01)
        return 0
    finally:
        try:
            sys.stdout.write("\n")
            sys.stdout.flush()
        except Exception:
            pass
        if stream_in is not None:
            try:
                stream_in.stop_stream()
                stream_in.close()
            except Exception:
                pass
        if stream_out is not None:
            try:
                stream_out.stop_stream()
                stream_out.close()
            except Exception:
                pass
        try:
            pa.terminate()
        except Exception:
            pass


def run() -> int:
    args = parse_args()
    if bool(args.vosk_list_models):
        print_models_catalog()
        return 0
    if bool(args.vosk_download_all_fr):
        return run_configure_only_flow(
            profile_path=Path(args.vosk_profile),
            cache_root=Path(args.vosk_cache_dir) if args.vosk_cache_dir else None,
            model_slug=None,
            interactive=False,
            list_only=False,
            download_all_fr=True,
        )
    if bool(args.vosk_configure_only):
        return run_configure_only_flow(
            profile_path=Path(args.vosk_profile),
            cache_root=Path(args.vosk_cache_dir) if args.vosk_cache_dir else None,
            model_slug=args.vosk_model_slug,
            interactive=bool(args.vosk_interactive),
            list_only=False,
        )
    if args.list_devices:
        return _list_devices()
    out_srt = Path(args.subtitle_out)
    if bool(args.dated_outfiles):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        out_dir = Path("scripts/modem_lab/generated/pc_headset_direct") / ts
        out_dir.mkdir(parents=True, exist_ok=True)
        out_srt = out_dir / "transcript.srt"
    try:
        ptt = _PushToTalkController(bool(args.push_to_talk), str(args.ptt_key))
        ptt.start()
        playback = _PlaybackQueue()
        rng = random.Random(int(args.prospection_seed)) if args.prospection_seed is not None else random.Random()
        intent_rels = list(args.prospection_intents_json or [])
        if not intent_rels and args.prospection_chain_preset == "danielcraft-outbound":
            intent_rels = list(DEFAULT_DANIELCRAFT_OUTBOUND_REL_CHAIN)
        pack_dir = Path(args.prospection_pack).resolve() if args.prospection_pack else None
        chain_paths = resolve_chain_paths(_REPO_ROOT, intent_rels) if intent_rels else []
        prospection_rows = merge_intent_chain_rows(chain_paths) if (pack_dir and chain_paths) else None
        if pack_dir and not chain_paths:
            logger.warning(
                "--prospection-pack sans JSON (--prospection-intents-json repetable ou "
                "--prospection-chain-preset=danielcraft-outbound)."
            )

        last_partial_ref: dict[str, str] = {"t": ""}

        def _partial_hook(t: str) -> None:
            if (
                bool(args.barge_in)
                and bool(args.barge_in_on_vosk_partial)
                and len((t or "").strip()) >= 2
            ):
                playback.clear()

        worker, model_dir = _resolve_vosk_worker(
            args,
            last_partial=last_partial_ref,
            partial_hook=_partial_hook,
        )
        trigger = None
        if bool(args.allo_trigger):
            trigger = KeywordIntentTrigger(
                [
                    KeywordTrigger(pattern=r"\b(all[oô]|oui\s+all[oô])\b", tag="allo", once=True),
                ]
            )

        if pack_dir and chain_paths:
            opening = _build_opening_with_prospection_pack(
                args, pack_dir=pack_dir, chain_json_paths=chain_paths, rng=rng
            )
        else:
            opening = _build_opening_pcm16(args)

        if bool(args.barge_in):
            barge_detector = _MicBargeInDetector(
                rms_threshold=float(args.barge_in_rms_threshold),
                speech_ms=float(args.barge_in_speech_ms),
                hangover_ms=float(args.barge_in_hangover_ms),
                sample_rate=RATE,
            )
            logger.info(
                "Barge-in actif (RMS seuil={}, parole min={} ms, repos={} ms, partial vosk={})",
                args.barge_in_rms_threshold,
                args.barge_in_speech_ms,
                args.barge_in_hangover_ms,
                bool(args.barge_in_on_vosk_partial),
            )
        else:
            barge_detector = None

        if prospection_rows:
            logger.info(
                "Prospection locale: pack={}, {} lignes intents (premier motif matche)",
                pack_dir,
                len(prospection_rows),
            )
        logger.info("Modele Vosk: {}", model_dir)
        worker.start()
        flusher = _SubtitleFlusher(worker=worker, out_srt=out_srt, flush_sec=float(args.subtitle_flush_sec))
        flusher.start()

        def _cleanup_vosk() -> None:
            try:
                worker.close_input()
                worker.join_utterances(timeout=8.0)
            except Exception:
                pass
            try:
                flusher.stop()
            except Exception:
                pass
            try:
                ptt.stop()
            except Exception:
                pass

        atexit.register(_cleanup_vosk)
        try:
            rc = _run_with_sounddevice(
                args,
                worker=worker,
                opening=opening,
                ptt=ptt,
                playback=playback,
                trigger=trigger,
                rng=rng,
                prospection_pack=pack_dir,
                prospection_rows=prospection_rows,
                barge_detector=barge_detector,
            )
        except Exception as e_sd:
            logger.debug("sounddevice indisponible/KO: {}", e_sd)
            rc = _run_with_pyaudio(
                args,
                worker=worker,
                opening=opening,
                ptt=ptt,
                playback=playback,
                trigger=trigger,
                rng=rng,
                prospection_pack=pack_dir,
                prospection_rows=prospection_rows,
                barge_detector=barge_detector,
            )
        finally:
            worker.close_input()
            try:
                worker.join_utterances(timeout=15.0)
            except Exception as e:
                logger.warning("Vosk join echoue: {}", e)
            flusher.stop()
            uts = worker.snapshot_utterances()
            if uts:
                write_subrip(out_srt, offset_timed_utterances(uts, 0.0))
                logger.info("Sous-titres ecrits: {}", out_srt)
            else:
                logger.warning("Aucun enonce final Vosk reconnu (SRT non ecrit).")
            atexit.unregister(_cleanup_vosk)
            ptt.stop()
        return rc
    except (KeyboardInterrupt, SystemExit):
        logger.warning("Interruption utilisateur")
        return 0
    except Exception as e:
        logger.error("Echec conversation locale: {}", e)
        return 2


if __name__ == "__main__":
    setup_logging("pc_headset_direct")
    raise SystemExit(run())
