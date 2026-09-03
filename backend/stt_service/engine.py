"""
Moteur STT singleton (charge une seule fois au demarrage).

Moteur choisi par STT_ENGINE=whisper (defaut) ou vosk.
Whisper : whisper-server (modele en RAM), sinon whisper-cli, sinon faster-whisper / openai-whisper.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from backend.voice.transcript_cues import build_transcript_cues

_engine: Optional[str] = None
_vosk_model = None
_whisper_model: Any = None
_whisper_backend: Optional[str] = None
_whisper_model_name: Optional[str] = None
_whisper_device: str = "cpu"
_last_cues: list[dict] = []
_last_segments: list[dict] = []

# Prompt FR telephonie : aide noms / numeros sans cout CPU notable.
_DEFAULT_FR_PROMPT = (
    "Messagerie telephonique francaise. Bonjour, Monsieur, Madame, entreprise, "
    "merci, a bientot, rappelez-moi au 0X XX XX XX XX."
)


def _env(name: str, default: str = "") -> str:
    """Lit une variable d'environnement, trimmee."""
    return (os.environ.get(name) or default).strip()


def selected_engine() -> str:
    """
    Moteur demande par la config.

    @returns whisper ou vosk.
    """
    raw = _env("STT_ENGINE", "whisper").lower()
    if raw not in ("whisper", "vosk"):
        raise RuntimeError(f"STT_ENGINE invalide: {raw} (whisper ou vosk).")
    return raw


def _resolve_vosk_model_path() -> str:
    """Resout le chemin du modele Vosk."""
    raw = _env("STT_VOSK_MODEL_PATH") or _env("VOSK_MODEL_PATH")
    if not raw:
        raise RuntimeError("STT_VOSK_MODEL_PATH ou VOSK_MODEL_PATH requis pour Vosk.")
    path = Path(raw)
    if not path.is_absolute():
        base = Path(_env("STT_BASE_PATH", "/opt/vocalguard-stt"))
        path = (base / raw).resolve()
    if not path.is_dir():
        raise RuntimeError(f"Modele Vosk introuvable: {path}")
    return str(path)


def _load_vosk() -> None:
    """Charge le modele Vosk en memoire."""
    global _vosk_model, _engine
    from vosk import Model

    model_path = _resolve_vosk_model_path()
    logger.info("STT service: chargement Vosk {}", model_path)
    _vosk_model = Model(model_path)
    _engine = "vosk"
    logger.info("STT service: Vosk pret")


def _cpu_supports_ctranslate2() -> bool:
    """
    faster-whisper/CTranslate2 exige souvent AVX. Un import sans AVX tue le process (SIGILL).

    @returns True si AVX est visible dans /proc/cpuinfo.
    """
    try:
        flags = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return " avx " in flags or "\tavx " in flags or " avx2 " in flags


def _resolve_whisper_cpp_paths() -> Optional[tuple[Path, Path]]:
    """
    Resout le binaire whisper-cli et le modele ggml si configures.

    @returns Tuple (binaire, modele) ou None si non configure.
    """
    cpp_bin = _env("STT_WHISPER_CPP_BIN")
    cpp_model = _env("STT_WHISPER_CPP_MODEL")
    if not cpp_bin or not cpp_model:
        return None
    bin_path = Path(cpp_bin)
    model_path = Path(cpp_model)
    if not model_path.is_absolute():
        base = Path(_env("STT_BASE_PATH", "/opt/vocalguard-stt"))
        model_path = (base / cpp_model).resolve()
    if not bin_path.is_file() or not model_path.is_file():
        raise RuntimeError(f"whisper.cpp introuvable: bin={bin_path} model={model_path}")
    return bin_path, model_path


def _whisper_decode_opts() -> dict[str, str]:
    """
    Options decode communes (greedy + prompt FR).

    @returns Dict beam_size, best_of, prompt, language, threads.
    """
    return {
        "language": _env("STT_WHISPER_LANGUAGE", "fr") or "fr",
        "threads": _env("STT_WHISPER_THREADS", "4") or "4",
        "beam_size": _env("STT_WHISPER_BEAM_SIZE", "1") or "1",
        "best_of": _env("STT_WHISPER_BEST_OF", "1") or "1",
        "prompt": _env("STT_WHISPER_PROMPT", _DEFAULT_FR_PROMPT) or _DEFAULT_FR_PROMPT,
    }


def _pcm_to_wav_bytes(audio_pcm: bytes, sample_rate: int) -> bytes:
    """
    Emballe du PCM 16-bit mono dans un conteneur WAV en memoire.

    @param audio_pcm PCM little-endian.
    @param sample_rate Taux (Hz).
    @returns Octets WAV.
    """
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_pcm)
    return buf.getvalue()


def _check_whisper_server(base_url: str, timeout_sec: float = 3.0) -> bool:
    """
    Verifie que whisper-server repond (page racine ou /inference).

    @param base_url URL de base (ex. http://127.0.0.1:8101).
    @param timeout_sec Delai max.
    @returns True si joignable.
    """
    import httpx

    url = base_url.rstrip("/")
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.get(f"{url}/")
            return resp.status_code < 500
    except Exception:
        return False


def _load_whisper() -> None:
    """
    Charge Whisper sans importer CTranslate2 sur CPU sans AVX (SIGILL).

    Ordre : whisper-server, whisper-cli, faster-whisper (AVX), openai-whisper.
    """
    global _whisper_model, _whisper_backend, _whisper_model_name, _whisper_device, _engine

    name = _env("STT_WHISPER_MODEL", "small") or "small"
    device = _env("STT_WHISPER_DEVICE", "cpu") or "cpu"
    compute = _env("STT_WHISPER_COMPUTE", "int8") or "int8"
    _whisper_model_name = name
    _whisper_device = device

    server_url = _env("STT_WHISPER_SERVER_URL").rstrip("/")
    if server_url:
        if not _check_whisper_server(server_url):
            raise RuntimeError(f"whisper-server injoignable: {server_url}")
        _whisper_model = {"server": server_url}
        _whisper_backend = "whisper.cpp-server"
        _engine = "whisper"
        logger.info("STT service: whisper-server pret {}", server_url)
        return

    cpp_paths = _resolve_whisper_cpp_paths()
    if cpp_paths is not None:
        bin_path, model_path = cpp_paths
        _whisper_model = {"bin": str(bin_path), "model": str(model_path)}
        _whisper_backend = "whisper.cpp"
        _engine = "whisper"
        logger.info("STT service: whisper.cpp pret bin={} model={}", bin_path, model_path)
        return

    if _cpu_supports_ctranslate2():
        try:
            from faster_whisper import WhisperModel

            logger.info(
                "STT service: chargement faster-whisper model={} device={} compute={}",
                name,
                device,
                compute,
            )
            _whisper_model = WhisperModel(name, device=device, compute_type=compute)
            _whisper_backend = "faster-whisper"
            _engine = "whisper"
            logger.info("STT service: Whisper pret ({})", name)
            return
        except Exception as exc:
            logger.warning("faster-whisper indisponible ({}), tentative openai-whisper", exc)
    else:
        logger.warning(
            "CPU sans AVX: faster-whisper ignore (SIGILL). "
            "Configurer STT_WHISPER_SERVER_URL ou STT_WHISPER_CPP_BIN/MODEL."
        )

    import warnings

    import whisper

    warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")
    logger.info("STT service: chargement openai-whisper model={} device={}", name, device)
    _whisper_model = whisper.load_model(name, device=device)
    _whisper_backend = "openai-whisper"
    _engine = "whisper"
    logger.info("STT service: Whisper pret ({})", name)


def load_model() -> None:
    """
    Charge le moteur STT configure (idempotent).

    @raises RuntimeError Si le modele est absent ou le moteur indisponible.
    """
    if _engine is not None:
        return
    engine = selected_engine()
    if engine == "whisper":
        _load_whisper()
        return
    _load_vosk()


def model_loaded() -> bool:
    """@returns True si un moteur est charge."""
    return _engine is not None


def engine_name() -> Optional[str]:
    """@returns whisper, vosk, ou None."""
    return _engine


def model_display() -> Optional[str]:
    """
    Identifiant lisible du modele charge.

    @returns Nom Whisper, chemin Vosk, ou None.
    """
    if _engine == "whisper":
        backend = _whisper_backend or "whisper"
        if _whisper_backend == "whisper.cpp-server" and isinstance(_whisper_model, dict):
            return f"whisper-server:{_whisper_model.get('server', '?')}"
        if _whisper_backend == "whisper.cpp" and isinstance(_whisper_model, dict):
            return f"whisper.cpp:{Path(_whisper_model.get('model', '')).name}"
        return f"{backend}:{_whisper_model_name or '?'}"
    if _engine == "vosk":
        try:
            return _resolve_vosk_model_path()
        except RuntimeError:
            return None
    return None


def _pcm16_to_float32(audio_pcm: bytes):
    """Convertit du PCM 16-bit little-endian en float32 [-1, 1]."""
    import numpy as np

    return np.frombuffer(audio_pcm, dtype=np.int16).astype(np.float32) / 32768.0


def _transcribe_whisper_server(audio_pcm: bytes, sample_rate: int) -> str:
    """
    Transcrit via whisper-server (modele deja en RAM).

    @param audio_pcm PCM 16-bit mono little-endian.
    @param sample_rate Taux d'echantillonnage (Hz).
    @returns Texte transcrit.
    """
    import httpx

    payload = _whisper_model or {}
    server = payload.get("server")
    if not server:
        raise RuntimeError("whisper-server non configure.")

    opts = _whisper_decode_opts()
    wav_bytes = _pcm_to_wav_bytes(audio_pcm, sample_rate)
    data = {
        "language": opts["language"],
        "beam_size": opts["beam_size"],
        "best_of": opts["best_of"],
        "temperature": "0.0",
        "temperature_inc": "0.0",
        "response_format": "verbose_json",
        "no_timestamps": "false",
    }
    if opts["prompt"]:
        data["prompt"] = opts["prompt"]
        data["carry_initial_prompt"] = "true"

    files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
    url = f"{server}/inference"
    with httpx.Client(timeout=300.0) as client:
        resp = client.post(url, data=data, files=files)
        if resp.status_code >= 400:
            raise RuntimeError(f"whisper-server HTTP {resp.status_code}: {resp.text[:500]}")
        body = resp.json()
        global _last_segments
        _last_segments = []
        if isinstance(body, dict):
            raw_segs = body.get("segments") or []
            if isinstance(raw_segs, list):
                _last_segments = [s for s in raw_segs if isinstance(s, dict)]
            text = (body.get("text") or "").strip()
            if text:
                return text
            parts = [(s.get("text") or "").strip() for s in _last_segments]
            return " ".join(p for p in parts if p).strip()
        return str(body).strip()


def _transcribe_whisper_cpp(audio_pcm: bytes, sample_rate: int) -> str:
    """
    Transcrit via whisper-cli (fallback si serveur absent).

    @param audio_pcm PCM 16-bit mono little-endian.
    @param sample_rate Taux d'echantillonnage (Hz).
    @returns Texte transcrit.
    """
    import subprocess
    import tempfile
    import wave

    payload = _whisper_model or {}
    bin_path = payload.get("bin")
    model_path = payload.get("model")
    if bin_path is None or model_path is None:
        raise RuntimeError("whisper.cpp non configure.")

    opts = _whisper_decode_opts()
    with tempfile.TemporaryDirectory(prefix="vg-whisper-") as tmp:
        wav_path = Path(tmp) / "audio.wav"
        out_prefix = Path(tmp) / "out"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_pcm)
        cmd = [
            str(bin_path),
            "-m",
            str(model_path),
            "-f",
            str(wav_path),
            "-l",
            opts["language"],
            "-otxt",
            "-of",
            str(out_prefix),
            "-np",
            "-nt",
            "-t",
            opts["threads"],
            "-bs",
            opts["beam_size"],
            "-bo",
            opts["best_of"],
            "--prompt",
            opts["prompt"],
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        txt_path = Path(f"{out_prefix}.txt")
        if txt_path.is_file():
            return txt_path.read_text(encoding="utf-8", errors="replace").strip()
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"whisper.cpp echec (code {proc.returncode}): {err[:500]}")


def _transcribe_whisper(audio_pcm: bytes) -> str:
    """
    Transcrit du PCM 16 kHz avec Whisper.

    @param audio_pcm PCM 16-bit mono little-endian.
    @returns Texte transcrit.
    """
    if _whisper_model is None:
        raise RuntimeError("Modele Whisper non charge.")
    if _whisper_backend == "whisper.cpp-server":
        return _transcribe_whisper_server(audio_pcm, sample_rate=16000)
    # whisper.cpp CLI: ne pas importer numpy (SIGILL sur CPU sans AVX, ex. T4400).
    if _whisper_backend == "whisper.cpp":
        return _transcribe_whisper_cpp(audio_pcm, sample_rate=16000)

    language = _env("STT_WHISPER_LANGUAGE", "fr") or "fr"
    audio = _pcm16_to_float32(audio_pcm)
    beam = int(_env("STT_WHISPER_BEAM_SIZE", "1") or "1")
    prompt = _env("STT_WHISPER_PROMPT", _DEFAULT_FR_PROMPT) or _DEFAULT_FR_PROMPT
    if _whisper_backend == "faster-whisper":
        global _last_segments
        collected: list[dict] = []
        parts: list[str] = []
        segments, _info = _whisper_model.transcribe(
            audio,
            language=language,
            beam_size=max(beam, 1),
            vad_filter=False,
            initial_prompt=prompt or None,
        )
        for seg in segments:
            t = (seg.text or "").strip()
            if not t:
                continue
            parts.append(t)
            collected.append(
                {
                    "start": float(getattr(seg, "start", 0) or 0),
                    "end": float(getattr(seg, "end", 0) or 0),
                    "text": t,
                }
            )
        _last_segments = collected
        return " ".join(parts).strip()

    result = _whisper_model.transcribe(
        audio,
        language=language,
        task="transcribe",
        fp16=False,
        initial_prompt=prompt or None,
    )
    return (result.get("text") or "").strip()


def _transcribe_vosk(audio_pcm: bytes, sample_rate: int) -> str:
    """
    Transcrit du PCM avec Vosk.

    @param audio_pcm PCM 16-bit mono little-endian.
    @param sample_rate Taux d'echantillonnage (Hz).
    @returns Texte transcrit.
    """
    if _vosk_model is None:
        raise RuntimeError("Modele Vosk non charge.")
    from vosk import KaldiRecognizer

    rec = KaldiRecognizer(_vosk_model, sample_rate)
    rec.SetWords(True)
    parts: list[str] = []
    chunk = 4000
    for i in range(0, len(audio_pcm), chunk):
        block = audio_pcm[i : i + chunk]
        if rec.AcceptWaveform(block):
            result = json.loads(rec.Result())
            t = (result.get("text") or "").strip()
            if t:
                parts.append(t)
    final = json.loads(rec.FinalResult())
    t = (final.get("text") or "").strip()
    if t:
        parts.append(t)
    return " ".join(parts).strip()


def last_cues() -> list[dict]:
    """
    Cues SRT de la derniere transcription (4-5 mots).

    @returns Liste serialisable, vide si aucune transcription.
    """
    return list(_last_cues)


def transcribe_pcm16(audio_pcm: bytes, sample_rate: int = 16000) -> str:
    """
    Transcrit du PCM 16-bit mono avec le moteur charge.

    @param audio_pcm Donnees PCM little-endian.
    @param sample_rate Taux d'echantillonnage (Hz).
    @returns Texte transcrit.
    """
    global _last_cues, _last_segments
    _last_cues = []
    _last_segments = []
    if not audio_pcm:
        return ""
    if _engine == "whisper":
        text = _transcribe_whisper(audio_pcm)
    elif _engine == "vosk":
        text = _transcribe_vosk(audio_pcm, sample_rate)
    else:
        raise RuntimeError("Moteur STT non charge.")
    duration = len(audio_pcm) / (2.0 * max(int(sample_rate), 1))
    _last_cues = build_transcript_cues(text, duration_sec=duration, segments=_last_segments)
    return text
