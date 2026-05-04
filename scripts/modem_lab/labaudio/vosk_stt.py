#!/usr/bin/env python3
"""
Reconnaissance vocale Vosk en temps réel dans un thread dédié + export sous-titres SUB / WebVTT.

Le flux attendu est du PCM **16-bit little-endian mono**, typiquement 8 kHz (ligne modem),
converti depuis l’u8 du VRX via ``labcore.live_audio.u8_pcm_to_s16le``.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger


def preload_vosk_model(model_path: str | Path, *, quiet: bool = True) -> Any:
    """
    Charge un modèle Vosk en amont et retourne l'objet ``Model``.

    Utile pour éviter un long temps mort au démarrage du thread STT.
    """
    from vosk import Model, SetLogLevel

    if quiet:
        try:
            SetLogLevel(-1)
        except Exception:
            pass
    p = Path(model_path)
    if not p.is_dir():
        raise FileNotFoundError(f"Modèle Vosk introuvable: {p}")
    return Model(str(p))


def _vrx_has_hangup_marker(blob: bytes) -> bool:
    """Marqueurs AT qui apparaissent quand le modem quitte le mode VRX."""
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


@dataclass(frozen=True)
class TimedWord:
    """Mot avec bornes en secondes **relatives au début de l’énoncé**."""

    start_sec: float
    end_sec: float
    word: str


@dataclass
class TimedUtterance:
    """Énoncé avec bornes **globales** dans le flux audio (secondes)."""

    start_sec: float
    end_sec: float
    text: str
    words: tuple[TimedWord, ...] = ()


def offset_timed_utterances(utterances: list[TimedUtterance], offset_sec: float) -> list[TimedUtterance]:
    """Décale les bornes des énoncés et des mots (alignement timeline / rapport ``t_speech_candidate``)."""
    if offset_sec == 0.0:
        return list(utterances)
    out: list[TimedUtterance] = []
    for u in utterances:
        words = tuple(
            TimedWord(
                start_sec=w.start_sec + offset_sec,
                end_sec=w.end_sec + offset_sec,
                word=w.word,
            )
            for w in u.words
        )
        out.append(
            TimedUtterance(
                start_sec=u.start_sec + offset_sec,
                end_sec=u.end_sec + offset_sec,
                text=u.text,
                words=words,
            )
        )
    return out


def _collapse_subtitle_text(text: str) -> str:
    """Une entrée SRT/VTT par bloc : évite les sauts de ligne parasites dans le texte STT."""
    return " ".join((text or "").replace("\n", " ").replace("\r", " ").split())


def format_timestamp_sub(sec: float) -> str:
    """Horodatage SubRip ``HH:MM:SS,mmm``."""
    if sec < 0:
        sec = 0.0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    whole = int(s)
    ms = int(round((s - whole) * 1000))
    if ms >= 1000:
        ms = 0
        whole += 1
        if whole >= 60:
            whole = 0
            m += 1
    return f"{h:02d}:{m:02d}:{whole:02d},{ms:03d}"


def format_timestamp_vtt(sec: float) -> str:
    """Horodatage WebVTT ``HH:MM:SS.mmm``."""
    if sec < 0:
        sec = 0.0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    whole = int(s)
    ms = int(round((s - whole) * 1000))
    if ms >= 1000:
        ms = 0
        whole += 1
    return f"{h:02d}:{m:02d}:{whole:02d}.{ms:03d}"


def write_subrip(path: Path, utterances: list[TimedUtterance], *, encoding: str = "utf-8") -> None:
    """Écrit un fichier ``.sub`` (format SubRip `.srt`)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i, u in enumerate(utterances, start=1):
        lines.append(str(i))
        lines.append(
            f"{format_timestamp_sub(u.start_sec)} --> {format_timestamp_sub(u.end_sec)}"
        )
        lines.append(_collapse_subtitle_text(u.text))
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding=encoding)


def write_webvtt(path: Path, utterances: list[TimedUtterance], *, encoding: str = "utf-8") -> None:
    """Écrit un fichier ``.vtt`` (WebVTT)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["WEBVTT", ""]
    for u in utterances:
        lines.append(
            f"{format_timestamp_vtt(u.start_sec)} --> {format_timestamp_vtt(u.end_sec)}"
        )
        lines.append(_collapse_subtitle_text(u.text))
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding=encoding)


def _parse_words(raw: list[dict[str, Any]]) -> tuple[TimedWord, ...]:
    out: list[TimedWord] = []
    for w in raw:
        try:
            word = str(w.get("word") or "").strip()
            start = float(w.get("start", 0.0))
            end = float(w.get("end", start))
            if word:
                out.append(TimedWord(start_sec=start, end_sec=end, word=word))
        except (TypeError, ValueError):
            continue
    return tuple(out)


def _utterance_from_result(
    result: dict[str, Any],
    offset_sec: float,
) -> tuple[Optional[TimedUtterance], float]:
    """
    Construit un énoncé à partir d’un JSON Vosk ``Result()`` / ``FinalResult()``.

    :returns: (utterance ou None, nouveau offset_sec)
    """
    text = (result.get("text") or "").strip()
    if not text:
        return None, offset_sec
    raw_words = result.get("result")
    words: tuple[TimedWord, ...] = ()
    if isinstance(raw_words, list) and raw_words:
        words = _parse_words(raw_words)
        if words:
            loc_start = min(w.start_sec for w in words)
            loc_end = max(w.end_sec for w in words)
            g0 = offset_sec + loc_start
            g1 = offset_sec + loc_end
            return (
                TimedUtterance(start_sec=g0, end_sec=g1, text=text, words=words),
                offset_sec + loc_end,
            )
    # Pas de timings mots : bloc court arbitraire pour garder une piste exploitable
    guess = 0.35 + min(0.12 * len(text.split()), 6.0)
    return (
        TimedUtterance(start_sec=offset_sec, end_sec=offset_sec + guess, text=text, words=words),
        offset_sec + guess,
    )


class VoskRealtimeWorker:
    """
    Consommateur PCM dans un thread : alimente ``KaldiRecognizer`` et collecte les énoncés.

    Utilisation ::
        w = VoskRealtimeWorker(model_path)
        w.start()
        try:
            w.push_pcm16(chunk)
        finally:
            w.close_input()
        utterances = w.join_utterances()
    """

    def __init__(
        self,
        model_path: str | Path,
        sample_rate: int = 8000,
        *,
        queue_max_chunks: int = 512,
        on_partial: Optional[Callable[[str], None]] = None,
        preloaded_model: Any | None = None,
    ) -> None:
        self._model_path = Path(model_path)
        self._sample_rate = int(sample_rate)
        self._q: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=max(8, int(queue_max_chunks)))
        self._on_partial = on_partial
        self._preloaded_model = preloaded_model
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[BaseException] = None
        self._utterances: list[TimedUtterance] = []
        self._lock = threading.Lock()
        self._offset_sec = 0.0

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("VoskRealtimeWorker déjà démarré")
        self._thread = threading.Thread(target=self._run, name="vosk-realtime", daemon=True)
        self._thread.start()

    def push_pcm16(self, pcm_s16le: bytes) -> None:
        """Enfile des octets PCM16 mono (bloquant si file pleine)."""
        self._q.put(pcm_s16le)

    def close_input(self) -> None:
        """Signal de fin de flux (obligatoire pour obtenir le ``FinalResult``)."""
        try:
            self._q.put_nowait(None)
        except queue.Full:
            self._q.put(None)

    def join_utterances(self, *, timeout: Optional[float] = None) -> list[TimedUtterance]:
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        if self._error is not None:
            raise self._error
        with self._lock:
            return list(self._utterances)

    def snapshot_utterances(self) -> list[TimedUtterance]:
        """Retourne une copie des énoncés déjà finalisés, sans arrêter le thread."""
        with self._lock:
            return list(self._utterances)

    def is_alive(self) -> bool:
        t = self._thread
        return bool(t and t.is_alive())

    def _run(self) -> None:
        try:
            from vosk import KaldiRecognizer, Model
        except ImportError as e:
            self._error = e
            logger.error("Paquet vosk manquant: pip install vosk")
            return

        if not self._model_path.is_dir():
            self._error = FileNotFoundError(f"Modèle Vosk introuvable: {self._model_path}")
            return

        try:
            model = self._preloaded_model if self._preloaded_model is not None else Model(str(self._model_path))
            rec = KaldiRecognizer(model, self._sample_rate)
            rec.SetWords(True)
        except Exception as e:
            self._error = e
            logger.exception("Init Vosk échouée")
            return

        offset_sec = 0.0
        while True:
            item = self._q.get()
            if item is None:
                break
            if not item:
                continue
            try:
                if rec.AcceptWaveform(item):
                    result = json.loads(rec.Result())
                    utt, offset_sec = _utterance_from_result(result, offset_sec)
                    if utt is not None:
                        with self._lock:
                            self._utterances.append(utt)
                        logger.debug("Vosk phrase: {}", utt.text[:120])
                else:
                    if self._on_partial:
                        partial = json.loads(rec.PartialResult())
                        ptxt = (partial.get("partial") or "").strip()
                        if ptxt:
                            self._on_partial(ptxt)
            except Exception as e:
                self._error = e
                logger.exception("Erreur traitement chunk Vosk")
                break

        try:
            final = json.loads(rec.FinalResult())
            utt, _ = _utterance_from_result(final, offset_sec)
            if utt is not None:
                with self._lock:
                    self._utterances.append(utt)
                logger.debug("Vosk finale: {}", utt.text[:120])
        except Exception as e:
            if self._error is None:
                self._error = e
            logger.exception("Vosk FinalResult")

        with self._lock:
            self._offset_sec = offset_sec


async def pump_vrx_pcm16_to_vosk(
    modem: Any,
    worker: VoskRealtimeWorker,
    *,
    max_seconds: float,
    chunk_size: int = 2048,
    idle_sleep_sec: float = 0.02,
    max_idle_sec: Optional[float] = None,
    stop_event: Optional[asyncio.Event] = None,
    stop_on_remote_hangup: bool = True,
    on_chunk_u8: Optional[Callable[[bytes], None]] = None,
) -> Optional[str]:
    """
    Lit ``read_vrx_chunk`` / ``read_outgoing_vrx_chunk``, convertit u8→s16le, alimente le worker.

    :returns: ``'remote_line_end'``, ``'idle_timeout'`` ou ``None``.
    """
    from labcore.live_audio import u8_pcm_to_s16le

    from labcore.call_watch import probe_remote_hangup_on_active_vrx

    read_fn = getattr(modem, "read_vrx_chunk", None)
    if read_fn is None:
        read_fn = modem.read_outgoing_vrx_chunk

    t0 = time.monotonic()
    t_last_chunk = t0
    idle_limit = float(max_idle_sec) if max_idle_sec is not None else 0.0
    tail = bytearray()
    carrier_initial = None
    try:
        conn = getattr(modem, "serial_connection", None)
        if conn is not None:
            carrier_initial = bool(conn.cd)
    except Exception:
        carrier_initial = None
    while True:
        if stop_event is not None and stop_event.is_set():
            break
        if time.monotonic() - t0 >= max_seconds:
            break

        chunk = await read_fn(chunk_size)
        if not chunk:
            if idle_limit > 0.0 and (time.monotonic() - t_last_chunk) >= idle_limit:
                return "idle_timeout"
            await asyncio.sleep(idle_sleep_sec)
            continue

        tail.extend(chunk)
        if len(tail) > 4096:
            del tail[:-4096]
        if stop_on_remote_hangup:
            try:
                if await probe_remote_hangup_on_active_vrx(
                    modem,
                    chunk_tail=bytes(tail),
                    carrier_initial=carrier_initial,
                ):
                    return "remote_line_end"
            except Exception:
                # Fallback minimal local si la sonde module échoue.
                if _vrx_has_hangup_marker(bytes(tail)):
                    return "remote_line_end"

        t_last_chunk = time.monotonic()
        if on_chunk_u8 is not None:
            try:
                on_chunk_u8(chunk)
            except Exception:
                # Le callback de capture ne doit jamais casser le pump STT.
                pass
        worker.push_pcm16(u8_pcm_to_s16le(chunk))
    return None
