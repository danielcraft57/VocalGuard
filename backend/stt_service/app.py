"""
Service HTTP STT VocalGuard (Whisper ou Vosk charge en permanence).

Lancement :
  STT_ENGINE=whisper STT_WHISPER_MODEL=small \\
  PYTHONPATH=/opt/vocalguard-stt uvicorn backend.stt_service.app:app --host 0.0.0.0 --port 8100
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel, Field

from backend.stt_service import engine as stt_engine
from backend.voice.audio_utils import load_wav_as_16k16bit_pcm


def _expected_token() -> Optional[str]:
    """Token interne LAN (optionnel en dev)."""
    return (os.environ.get("STT_INTERNAL_TOKEN") or "").strip() or None


def _check_token(header: Optional[str]) -> None:
    """
    Verifie le token interne si configure.

    @param header Valeur du header X-STT-Token.
    @raises HTTPException Si token invalide.
    """
    expected = _expected_token()
    if not expected:
        return
    if (header or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Token STT invalide.")


class TranscribeResponse(BaseModel):
    """Reponse transcription fichier."""

    text: str = Field(default="", description="Texte transcrit.")
    bytes_pcm: int = Field(default=0, description="Octets PCM 16 kHz traites.")
    engine: str = Field(default="", description="Moteur utilise (whisper ou vosk).")
    cues: list[dict] = Field(default_factory=list, description="Cues SRT 4-5 mots.")


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Charge le moteur STT au demarrage du service."""
    stt_engine.load_model()
    yield


app = FastAPI(title="VocalGuard STT", version="1.0.0", lifespan=_lifespan)


@app.get("/health")
async def health() -> dict:
    """Etat du service et du modele."""
    return {
        "status": "ok" if stt_engine.model_loaded() else "loading",
        "engine": stt_engine.engine_name(),
        "model_loaded": stt_engine.model_loaded(),
        "model": stt_engine.model_display(),
        "model_path": stt_engine.model_display(),
    }


@app.post("/v1/transcribe", response_model=TranscribeResponse)
async def transcribe_file(
    file: UploadFile = File(...),
    x_stt_token: Optional[str] = Header(None, alias="X-STT-Token"),
) -> TranscribeResponse:
    """
    Transcrit un fichier audio (WAV recommande, 8 ou 16 kHz).

    @param file Fichier audio multipart.
    @param x_stt_token Token interne optionnel.
    @returns Texte transcrit.
    """
    _check_token(x_stt_token)
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide.")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        pcm = await asyncio.to_thread(load_wav_as_16k16bit_pcm, tmp_path)
        text = await asyncio.to_thread(stt_engine.transcribe_pcm16, pcm, 16000)
        logger.info("STT fichier {} -> {} car.", file.filename, len(text))
        return TranscribeResponse(
            text=text,
            bytes_pcm=len(pcm),
            engine=stt_engine.engine_name() or "",
            cues=stt_engine.last_cues(),
        )
    except Exception as exc:
        logger.exception("STT fichier echoue: {}", exc)
        raise HTTPException(status_code=422, detail=f"Transcription impossible: {exc}") from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
