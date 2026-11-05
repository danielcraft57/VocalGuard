"""
Pipeline micro → STT node15 → Qdrant → fetch WAV node14.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx
import numpy as np
import sounddevice as sd

from desktop.audio_core import (
    AUDIO_RATE,
    input_device_candidates,
    output_device_candidates,
    pcm16_from_f32,
    prepare_studio_playback,
    read_studio_float,
    read_wav_mono_f32,
)
from desktop.studio_env import bootstrap_stt_from_api, load_studio_env, normalize_voice_api
from desktop.speech_gate import AmbientSpeechGate, bandpass_voice_mono
from desktop.studio_recording import FilteredWavArchive

DEFAULT_STT = os.environ.get("VG_STT_URL", "http://node15.lan:8100").rstrip("/")
DEFAULT_VOICE = os.environ.get(
    "VG_VOICE_API", "http://node14.lan:8000/api/v1"
).rstrip("/")


def _stt_transcribe_mode() -> str:
    """
    Mode STT node15 : live (rapide) ou final (timestamps, plus lent).

    @returns live ou final.
    """
    raw = (os.environ.get("VG_STT_TRANSCRIBE_MODE") or "live").strip().lower()
    if raw not in ("live", "final"):
        return "live"
    return raw


def _stt_token_from_env() -> str:
    """Token header X-STT-Token."""
    return (
        os.environ.get("VG_STT_TOKEN") or os.environ.get("STT_INTERNAL_TOKEN") or ""
    ).strip()


def ensure_studio_credentials(voice_api: str = DEFAULT_VOICE) -> None:
    """
    Charge studio.env puis token STT depuis node14 si besoin.

    @param voice_api Base API node14.
    """
    load_studio_env()
    base = normalize_voice_api(
        os.environ.get("VG_VOICE_API", voice_api) or DEFAULT_VOICE
    )
    os.environ["VG_VOICE_API"] = base
    bootstrap_stt_from_api(base)


@dataclass
class PipelineResult:
    """Resultat d'un tour micro → reponse vocale."""

    prospect_text: str = ""
    engine: str = ""
    tag: Optional[str] = None
    score: float = 0.0
    reply: str = ""
    wav_basename: Optional[str] = None
    top_predictions: List[Dict[str, Any]] = field(default_factory=list)


class CommercialPipeline:
    """
    Client HTTP STT + predict + lecture WAV.

    @param stt_url Base node15 (:8100).
    @param voice_api Base node14 API (:8000/api/v1).
    @param stt_token Header X-STT-Token optionnel.
    """

    def __init__(
        self,
        stt_url: str = DEFAULT_STT,
        voice_api: str = DEFAULT_VOICE,
        stt_token: Optional[str] = None,
    ) -> None:
        ensure_studio_credentials(voice_api)
        token = (stt_token if stt_token is not None else _stt_token_from_env()).strip()
        self.stt_url = (
            os.environ.get("VG_STT_URL", stt_url) or DEFAULT_STT
        ).rstrip("/")
        self.voice_api = normalize_voice_api(
            os.environ.get("VG_VOICE_API", voice_api) or DEFAULT_VOICE
        )
        os.environ["VG_VOICE_API"] = self.voice_api
        self._stop_play = threading.Event()
        headers = {"X-STT-Token": token} if token else {}
        self.stt = httpx.Client(base_url=self.stt_url, timeout=180.0, headers=headers)
        self.voice = httpx.Client(base_url=self.voice_api, timeout=120.0)
        self.recent_tags: List[str] = []
        self.recent_replies: List[str] = []
        self.mic_gain = max(0.1, min(3.0, read_studio_float("VG_STUDIO_MIC_GAIN", 1.0)))
        self.play_gain = max(0.05, min(1.0, read_studio_float("VG_STUDIO_PLAY_GAIN", 0.35)))
        self.wav_archive: Optional[FilteredWavArchive] = None

    def attach_wav_archive(self, archive: FilteredWavArchive) -> None:
        """
        Branche l'archivage WAV filtre local.

        @param archive Session d'enregistrement.
        """
        self.wav_archive = archive

    def _persist_filtered_wav(self, mono: np.ndarray, label: str) -> Optional[Path]:
        """
        Enregistre le mono filtre si archive active.

        @param mono Audio post-filtre.
        @param label Nom logique du clip.
        @returns Chemin ou None.
        """
        if self.wav_archive is None or len(mono) < 1:
            return None
        return self.wav_archive.save_filtered(mono, label)

    def reload_stt_client(self) -> None:
        """Recharge le client STT apres changement studio.env / sync node14."""
        ensure_studio_credentials(self.voice_api)
        token = _stt_token_from_env()
        headers = {"X-STT-Token": token} if token else {}
        self.stt_url = (os.environ.get("VG_STT_URL") or self.stt_url).rstrip("/")
        try:
            self.stt.close()
        except Exception:
            pass
        self.stt = httpx.Client(
            base_url=self.stt_url, timeout=180.0, headers=headers
        )

    def stop_playback(self) -> None:
        """Interrompt une lecture audio bloquee."""
        self._stop_play.set()
        try:
            sd.stop()
        except Exception:
            pass

    def _check_stt_response(self, res: httpx.Response, action: str) -> None:
        """
        @raises RuntimeError Message clair (401 token, etc.).
        """
        if res.status_code == 401:
            raise RuntimeError(
                "Token STT refuse par node15. "
                "Verifiez STT_INTERNAL_TOKEN (node14 = node15) ou creez studio.env "
                "avec VG_STT_TOKEN=... a cote de l'exe. "
                "Whisper fonctionne ; c'est la protection HTTP du service :8100."
            )
        if res.status_code >= 400:
            raise RuntimeError(res.text or f"{action} HTTP {res.status_code}")

    def close(self) -> None:
        """Ferme les clients HTTP."""
        self.stt.close()
        self.voice.close()

    def reset_dialogue(self) -> None:
        """Reinitialise le fil persona."""
        self.recent_tags.clear()
        self.recent_replies.clear()

    def record_pcm(
        self,
        seconds: float,
        device: Optional[int],
        level_callback: Optional[Callable[[float], None]] = None,
    ) -> np.ndarray:
        """
        Capture mono float32 avec callback niveau optionnel.

        @param seconds Duree.
        @param device Index micro.
        @param level_callback Appelle avec RMS 0..1 environ chaque bloc.
        @returns Buffer (n,).
        """
        frames: list[np.ndarray] = []

        def _cb(indata, _frames, _time, status) -> None:  # noqa: ANN001
            if status:
                pass
            mono = indata[:, 0].copy()
            frames.append(mono)
            if level_callback is not None:
                rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
                rms *= self.mic_gain
                level_callback(min(1.0, rms * 8.0))

        last_err: Optional[Exception] = None
        for dev in input_device_candidates(device):
            frames.clear()
            try:
                with sd.InputStream(
                    samplerate=AUDIO_RATE,
                    channels=1,
                    dtype="float32",
                    device=dev,
                    callback=_cb,
                    blocksize=int(AUDIO_RATE * 0.05),
                ):
                    sd.sleep(int(seconds * 1000))
                if frames:
                    mono = np.concatenate(frames)
                    if abs(self.mic_gain - 1.0) > 0.01:
                        mono = np.clip(mono * self.mic_gain, -1.0, 1.0)
                    gate = AmbientSpeechGate()
                    if gate.enabled:
                        cleaned = gate.prepare_stt_chunk(mono)
                        if cleaned is None:
                            raise RuntimeError(
                                "Peu ou pas de voix detectee (TV/musique ?). "
                                "Parlez plus pres du micro ou desactivez Filtre ambiance."
                            )
                        mono = cleaned
                    else:
                        mono = bandpass_voice_mono(mono)
                    self._persist_filtered_wav(mono, "record_tour")
                    return mono
            except Exception as exc:
                last_err = exc
                continue

        raise RuntimeError(
            "Micro inaccessible (périphérique invalide ou occupé). "
            "Changez le micro dans la liste ou branchez un casque Hands-Free. "
            f"Detail : {last_err}"
        )

    def transcribe_pcm(self, mono: np.ndarray) -> str:
        """
        Envoie un WAV 16 kHz au STT node15.

        @param mono Echantillons float32.
        @returns Texte transcrit.
        """
        pcm = pcm16_from_f32(mono)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)
        try:
            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(AUDIO_RATE)
                wf.writeframes(pcm)
            with wav_path.open("rb") as f:
                files = {"file": ("prospect.wav", f, "audio/wav")}
                res = self.stt.post(
                    "/v1/transcribe",
                    files=files,
                    params={"mode": _stt_transcribe_mode()},
                )
            self._check_stt_response(res, "STT")
            text = (res.json().get("text") or "").strip()
            if not text:
                raise RuntimeError("STT vide — parlez plus fort.")
            return text
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                pass

    def predict(
        self,
        text: str,
        *,
        force_tag: Optional[str] = None,
        variant_index: Optional[int] = None,
    ) -> PipelineResult:
        """
        Predict Qdrant commercial via node14 (Postgres + Qdrant node15).

        @param text Parole prospect.
        @param force_tag Intent force (presentation).
        @param variant_index Variante 0..4.
        @returns PipelineResult enrichi.
        """
        body: Dict[str, Any] = {
            "text": text,
            "top_k": 8,
            "recent_tags": self.recent_tags,
            "recent_replies": self.recent_replies,
        }
        if force_tag:
            body["force_tag"] = force_tag
        if variant_index is not None:
            body["variant_index"] = variant_index
        res = self.voice.post("/kb/outbound-commercial/predict", json=body)
        if res.status_code >= 400:
            detail = res.text or f"Predict HTTP {res.status_code}"
            if "DATABASE_URL" in detail:
                detail = (
                    "Predict indisponible sur l'API node14. "
                    "Verifiez QDRANT_URL et Postgres sur node14."
                )
            raise RuntimeError(detail)
        data = res.json()
        result = PipelineResult(
            prospect_text=text,
            engine=str(data.get("engine") or ""),
            tag=data.get("tag"),
            score=float(data.get("score") or 0.0),
            reply=str(data.get("reply") or ""),
            wav_basename=data.get("wav_basename"),
            top_predictions=list(data.get("top_predictions") or []),
        )
        if result.tag:
            self.recent_tags.append(str(result.tag))
            if result.reply:
                self.recent_replies.append(result.reply)
            self.recent_tags = self.recent_tags[-24:]
            self.recent_replies = self.recent_replies[-24:]
        return result

    def download_wav(self, basename: str) -> Path:
        """
        Telecharge le WAV commercial depuis node14.

        @param basename Sans extension.
        @returns Chemin temporaire local.
        """
        res = self.voice.get(f"/kb/outbound-commercial/voice/{basename}", timeout=45.0)
        if res.status_code == 404:
            raise RuntimeError(f"WAV introuvable : {basename}")
        if res.status_code >= 400:
            raise RuntimeError(
                f"WAV indisponible ({res.status_code}) sur {self.voice_api}. "
                "Verifiez VG_VOICE_API=http://node14.lan:8000/api/v1 (pas :8090)."
            )
        if len(res.content) < 200:
            raise RuntimeError(f"Fichier WAV vide ou trop court : {basename}")

        tmp_fd, tmp_name = tempfile.mkstemp(suffix=".wav")
        os.close(tmp_fd)
        tmp = Path(tmp_name)
        tmp.write_bytes(res.content)
        return tmp

    def play_wav(
        self,
        path: Path,
        device: Optional[int],
        level_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Lit un fichier WAV sur la sortie audio.

        @param path Fichier local.
        @param device Index HP.
        @param level_callback RMS pendant lecture.
        """
        self._stop_play.clear()
        audio, file_rate = read_wav_mono_f32(path)
        audio, play_rate = prepare_studio_playback(
            audio, file_rate, gain=self.play_gain
        )

        duration_sec = len(audio) / float(max(play_rate, 1))
        last_err: Optional[Exception] = None
        for dev in output_device_candidates(device):
            if self._stop_play.is_set():
                raise RuntimeError("Lecture annulée.")
            try:

                def _play_once() -> None:
                    sd.play(audio, samplerate=play_rate, device=dev)
                    sd.wait()

                thread = threading.Thread(target=_play_once, daemon=True)
                thread.start()
                deadline = time.monotonic() + duration_sec + 10.0
                while thread.is_alive():
                    if self._stop_play.is_set():
                        sd.stop()
                        raise RuntimeError("Lecture annulée.")
                    if time.monotonic() > deadline:
                        sd.stop()
                        raise RuntimeError(
                            "Lecture bloquée sur cette sortie audio. "
                            "Choisissez « Haut-parleurs » ou un casque Stereo, puis Actualiser."
                        )
                    thread.join(timeout=0.15)
                if level_callback is not None:
                    level_callback(0.85)
                return
            except Exception as exc:
                last_err = exc
                if "annulée" in str(exc).lower():
                    raise
        raise RuntimeError(
            f"Sortie audio inaccessible. Detail : {last_err}"
        )
