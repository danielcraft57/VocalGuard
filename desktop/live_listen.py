"""
Ecoute micro continue : envoi Whisper par chunks + fin de tour au silence.
"""

from __future__ import annotations

import os
import queue
import threading
from typing import List, Optional, TYPE_CHECKING

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QThread, Signal

if TYPE_CHECKING:
    from desktop.commercial_pipeline import CommercialPipeline

from backend.voice.turn_vad import TurnVad, TurnVadConfig
from desktop.audio_core import AUDIO_RATE, input_device_candidates, pcm16_from_f32
from desktop.speech_gate import AmbientSpeechGate, bandpass_voice_mono, env_float


def _live_vad_config() -> TurnVadConfig:
    """
    Seuils VAD bureau (PCM 16 kHz).

    @returns Configuration TurnVad.
    """
    try:
        rms = float(os.environ.get("VG_LIVE_VAD_RMS", "280"))
    except ValueError:
        rms = 280.0
    try:
        silence_ms = float(os.environ.get("VG_LIVE_SILENCE_MS", "750"))
    except ValueError:
        silence_ms = 750.0
    return TurnVadConfig(
        speech_rms_threshold=max(80.0, rms),
        turn_silence_ms=max(300.0, silence_ms),
    )


def _live_chunk_seconds() -> float:
    """Duree d'un chunk envoye a Whisper pendant la parole."""
    try:
        sec = float(os.environ.get("VG_LIVE_CHUNK_SEC", "2.0"))
    except ValueError:
        sec = 2.0
    return max(0.8, min(6.0, sec))


class LiveSttChunkWorker(QThread):
    """
    File STT : transcrit les chunks un par un (Whisper live sur node15).

    @param pipeline Client CommercialPipeline partage.
    """

    partial_text = Signal(str)
    failed = Signal(str)

    def __init__(self, pipeline) -> None:  # noqa: ANN001
        super().__init__()
        self.pipeline = pipeline
        self._q: queue.Queue[Optional[np.ndarray]] = queue.Queue(maxsize=32)
        self._stop = threading.Event()
        self._parts: List[str] = []

    def clear_session(self) -> None:
        """Nouveau tour de parole (apres reponse Marie)."""
        self._parts.clear()
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def submit(self, mono: np.ndarray) -> None:
        """
        Enfile un morceau audio pour STT.

        @param mono Float32 mono 16 kHz.
        """
        if mono is None or len(mono) < int(AUDIO_RATE * 0.25):
            return
        try:
            self._q.put_nowait(mono.copy())
        except queue.Full:
            pass

    def stop(self) -> None:
        """Arrete le worker."""
        self._stop.set()
        try:
            self._q.put_nowait(None)
        except queue.Full:
            pass

    def joined_text(self) -> str:
        """Texte cumule des chunks deja transcrits."""
        return " ".join(p for p in self._parts if p).strip()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                mono = self._q.get(timeout=0.25)
            except queue.Empty:
                continue
            if mono is None:
                break
            try:
                text = self.pipeline.transcribe_pcm(mono).strip()
                if text:
                    self._parts.append(text)
                    self.partial_text.emit(self.joined_text())
            except Exception as exc:
                self.failed.emit(str(exc))


class LiveListenWorker(QThread):
    """
    Micro ouvert : emet des chunks STT reguliers puis le tour complet au silence.

    @param mic_gain Gain micro (meme reglage que le Studio).
    @param device Index PortAudio entree.
    """

    level = Signal(float)
    stt_chunk = Signal(object)
    utterance = Signal(object)
    status = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        device: Optional[int],
        *,
        mic_gain: float = 1.0,
        pipeline: Optional["CommercialPipeline"] = None,
    ) -> None:
        super().__init__()
        self.device = device
        self.mic_gain = max(0.1, min(3.0, float(mic_gain)))
        self._pipeline = pipeline
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._chunk_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=256)
        self._stream: Optional[sd.InputStream] = None
        self._chunk_samples = int(AUDIO_RATE * _live_chunk_seconds())

    def stop(self) -> None:
        """Arrete la capture."""
        self._stop.set()
        try:
            if self._stream is not None:
                self._stream.stop()
        except Exception:
            pass

    def pause(self) -> None:
        """Suspend l'accumulation (pendant reponse Marie)."""
        self._paused.set()

    def resume(self) -> None:
        """Reprend l'ecoute."""
        self._paused.clear()
        while not self._chunk_q.empty():
            try:
                self._chunk_q.get_nowait()
            except queue.Empty:
                break

    def run(self) -> None:
        """Boucle capture + VAD + chunks."""
        vad = TurnVad(_live_vad_config())
        gate = AmbientSpeechGate()
        frames: List[np.ndarray] = []
        pending_chunk: List[np.ndarray] = []
        pending_samples = 0
        user_speech_ms = 0.0
        user_silence_ms = 0.0
        turn_silence_ms = _live_vad_config().turn_silence_ms
        min_samples = int(AUDIO_RATE * 0.35)
        max_samples = int(AUDIO_RATE * 18.0)
        frame_ms = 50.0
        last_err: Optional[Exception] = None
        chunk_sec = _live_chunk_seconds()

        def _archive(label: str, mono: np.ndarray) -> None:
            if self._pipeline is not None:
                self._pipeline._persist_filtered_wav(mono, label)

        def _callback(indata, _frames, _time, status) -> None:  # noqa: ANN001
            if self._stop.is_set() or self._paused.is_set():
                return
            if status:
                pass
            mono = np.clip(indata[:, 0].astype(np.float32) * self.mic_gain, -1.0, 1.0)
            rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
            self.level.emit(min(1.0, rms * 8.0))
            try:
                self._chunk_q.put_nowait(mono)
            except queue.Full:
                pass

        for dev in input_device_candidates(self.device):
            if self._stop.is_set():
                break
            frames.clear()
            pending_chunk.clear()
            pending_samples = 0
            user_speech_ms = 0.0
            user_silence_ms = 0.0
            gate.reset()
            vad.reset()
            try:
                self.status.emit(
                    f"Live — chunks {chunk_sec:.1f}s, filtre ambiance actif, "
                    "parlez pres du micro."
                )
                with sd.InputStream(
                    samplerate=AUDIO_RATE,
                    channels=1,
                    dtype="float32",
                    device=dev,
                    callback=_callback,
                    blocksize=int(AUDIO_RATE * 0.05),
                ) as stream:
                    self._stream = stream
                    while not self._stop.is_set():
                        try:
                            block = self._chunk_q.get(timeout=0.15)
                        except queue.Empty:
                            continue
                        frames.append(block)
                        filtered = (
                            bandpass_voice_mono(block)
                            if gate.enabled
                            else block
                        )
                        speech = gate.is_speech_block(block)
                        pcm = pcm16_from_f32(filtered)
                        if speech:
                            user_speech_ms += frame_ms
                            user_silence_ms = 0.0
                            vad.feed_buffer(
                                pcm, sample_rate=AUDIO_RATE, frame_ms=frame_ms
                            )
                        else:
                            if user_speech_ms > 0:
                                user_silence_ms += frame_ms
                            vad.feed_buffer(
                                pcm, sample_rate=AUDIO_RATE, frame_ms=frame_ms
                            )

                        if speech:
                            pending_chunk.append(filtered)
                            pending_samples += len(filtered)
                            if pending_samples >= self._chunk_samples:
                                mono_chunk = np.concatenate(pending_chunk)
                                pending_chunk.clear()
                                pending_samples = 0
                                ready = gate.prepare_stt_chunk(mono_chunk)
                                if ready is not None:
                                    _archive("live_chunk", ready)
                                    self.stt_chunk.emit(ready)

                        turn_end = (
                            user_speech_ms >= 350.0
                            and user_silence_ms >= turn_silence_ms
                        ) or vad.ended
                        if not turn_end and sum(len(f) for f in frames) > max_samples:
                            turn_end = True

                        if turn_end:
                            mono = (
                                np.concatenate(frames)
                                if frames
                                else np.array([], dtype=np.float32)
                            )
                            frames.clear()
                            pending_chunk.clear()
                            pending_samples = 0
                            user_speech_ms = 0.0
                            user_silence_ms = 0.0
                            vad.reset()
                            gate.reset()
                            if len(mono) >= min_samples:
                                final = gate.prepare_stt_chunk(mono) or mono
                                if gate.speech_ratio(final) >= env_float(
                                    "VG_LIVE_UTTERANCE_SPEECH_RATIO", 0.22
                                ):
                                    _archive("live_utterance", final)
                                    self.utterance.emit(final)
                return
            except Exception as exc:
                last_err = exc
                frames.clear()
                pending_chunk.clear()
                vad.reset()
                continue
            finally:
                self._stream = None

        if not self._stop.is_set():
            self.failed.emit(
                f"Micro live indisponible. Detail : {last_err or 'inconnu'}"
            )
