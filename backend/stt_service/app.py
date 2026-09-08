"""
Service HTTP STT / TTS / intent VocalGuard (node15).

Lancement :
  STT_ENGINE=whisper STT_WHISPER_MODEL=base \\
  DATABASE_URL=postgresql+psycopg2://... \\
  PYTHONPATH=/opt/vocalguard-stt uvicorn backend.stt_service.app:app --host 0.0.0.0 --port 8100
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, List, Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
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
    mode: str = Field(default="final", description="live ou final.")


class IntentPredictRequest(BaseModel):
    """Corps predict intent."""

    text: str = Field(..., description="Texte cumule a classer.")
    top_k: int = Field(default=8, ge=1, le=32)


class IntentPredictResponse(BaseModel):
    """Scores d'intents."""

    top_predictions: List[dict] = Field(default_factory=list)


class TtsRequest(BaseModel):
    """Synthese vocale edge-tts."""

    text: str
    voice: str = "fr-FR-DeniseNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"


def _form_float(raw: Optional[str], default: float) -> float:
    """Parse un float formulaire, sinon defaut."""
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _form_int(raw: Optional[str], default: int) -> int:
    """Parse un int formulaire, sinon defaut."""
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Charge le moteur STT au demarrage du service."""
    stt_engine.load_model()
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if db_url:
        try:
            from backend.database import database as db_module

            await db_module.init_database(db_url)
            logger.info("STT service: DATABASE_URL OK pour intent-predict")
        except Exception as exc:
            logger.warning("STT service: init DB ignoree ({})", exc)
    yield


app = FastAPI(title="VocalGuard STT", version="1.2.0", lifespan=_lifespan)


@app.get("/health")
async def health() -> dict:
    """Etat du service et du modele."""
    return {
        "status": "ok" if stt_engine.model_loaded() else "loading",
        "engine": stt_engine.engine_name(),
        "model_loaded": stt_engine.model_loaded(),
        "model": stt_engine.model_display(),
        "model_path": stt_engine.model_display(),
        "features": ["transcribe", "intent-predict", "tts", "greeting-mix"],
    }


@app.post("/v1/transcribe", response_model=TranscribeResponse)
async def transcribe_file(
    file: UploadFile = File(...),
    mode: str = Query(default="final", description="live ou final"),
    x_stt_token: Optional[str] = Header(None, alias="X-STT-Token"),
) -> TranscribeResponse:
    """
    Transcrit un fichier audio (WAV recommande, 8 ou 16 kHz).

    @param file Fichier audio multipart.
    @param mode live (rapide) ou final.
    @param x_stt_token Token interne optionnel.
    @returns Texte transcrit.
    """
    _check_token(x_stt_token)
    mode_n = (mode or "final").strip().lower()
    if mode_n not in ("live", "final"):
        mode_n = "final"
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide.")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        pcm = await asyncio.to_thread(load_wav_as_16k16bit_pcm, tmp_path)
        text = await asyncio.to_thread(
            stt_engine.transcribe_pcm16,
            pcm,
            16000,
            fast=(mode_n == "live"),
        )
        logger.info("STT ({}) fichier {} -> {} car.", mode_n, file.filename, len(text))
        return TranscribeResponse(
            text=text,
            bytes_pcm=len(pcm),
            engine=stt_engine.engine_name() or "",
            cues=stt_engine.last_cues() if mode_n == "final" else [],
            mode=mode_n,
        )
    except Exception as exc:
        logger.exception("STT fichier echoue: {}", exc)
        raise HTTPException(status_code=422, detail=f"Transcription impossible: {exc}") from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


@app.post("/v1/intent-predict", response_model=IntentPredictResponse)
async def intent_predict(
    body: IntentPredictRequest,
    x_stt_token: Optional[str] = Header(None, alias="X-STT-Token"),
) -> IntentPredictResponse:
    """
    Predict vectoriel des intents (Postgres + embeddings).

    @param body Texte cumule.
    @returns top_predictions.
    """
    _check_token(x_stt_token)
    from backend.database import database as db_module
    from backend.services import intent_repository as intent_repo

    if db_module.SessionLocal is None:
        raise HTTPException(
            status_code=503,
            detail="DATABASE_URL non configuree sur le service STT.",
        )
    db = db_module.SessionLocal()
    try:
        preds = await asyncio.to_thread(
            intent_repo.predict_intent_scores,
            db,
            body.text,
            top_k=body.top_k,
        )
        return IntentPredictResponse(top_predictions=preds)
    finally:
        db.close()


@app.post("/v1/tts")
async def tts_synthesize(
    body: TtsRequest,
    x_stt_token: Optional[str] = Header(None, alias="X-STT-Token"),
) -> Response:
    """
    Synthese edge-tts (MP3) pour prefetch KB.

    @param body Texte + params voix.
    @returns audio/mpeg.
    """
    _check_token(x_stt_token)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Texte vide.")
    try:
        import edge_tts
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="edge-tts non installe") from exc

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        communicate = edge_tts.Communicate(
            text,
            body.voice or "fr-FR-DeniseNeural",
            rate=body.rate or "+0%",
            pitch=body.pitch or "+0Hz",
        )
        await communicate.save(str(tmp_path))
        data = tmp_path.read_bytes()
        if not data:
            raise HTTPException(status_code=422, detail="TTS vide")
        return Response(content=data, media_type="audio/mpeg")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("TTS echoue: {}", exc)
        raise HTTPException(status_code=422, detail=f"TTS impossible: {exc}") from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


@app.post("/v1/greeting-mix")
async def greeting_mix(
    text: str = Form(...),
    voice: str = Form(default="fr-FR-DeniseNeural"),
    rate: str = Form(default="+0%"),
    pitch: str = Form(default="+0Hz"),
    tts_voice_gain_db: str = Form(default="-6.0"),
    intro_mode: str = Form(default="none"),
    intro_variant: str = Form(default="tesla"),
    intro_sec: str = Form(default="2.2"),
    crossfade_ms: str = Form(default="380"),
    voice_bed_db: str = Form(default="-18.0"),
    voice_mix_gain_db: str = Form(default="0.0"),
    track_duck_db: str = Form(default="0.0"),
    music_offset_sec: str = Form(default="0.0"),
    bed_variant: str = Form(default=""),
    sample_rate: str = Form(default="11025"),
    sample_width: str = Form(default="2"),
    append_beep: str = Form(default="1"),
    beep_gap_ms: str = Form(default="500"),
    output: str = Form(default="modem"),
    intro_file: Optional[UploadFile] = File(default=None),
    beep_file: Optional[UploadFile] = File(default=None),
    x_stt_token: Optional[str] = Header(None, alias="X-STT-Token"),
) -> Response:
    """
    TTS edge-tts + mix intro/voix (+ bip) pour accueil incoming-audio.

    @returns audio/wav (modem ou apercu listen selon ``output``).
    """
    _check_token(x_stt_token)
    speak = (text or "").strip()
    if not speak:
        raise HTTPException(status_code=400, detail="Texte vide.")

    try:
        import edge_tts
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="edge-tts non installe") from exc

    from backend.voice.greeting_mix_builder import GreetingMixParams, build_greeting_mix_from_tts_source
    from backend.voice.synthesis import _wrap_edge_ssml_if_needed

    voice_id = (voice or "fr-FR-DeniseNeural").strip() or "fr-FR-DeniseNeural"
    out_mode = (output or "modem").strip().lower()
    if out_mode not in ("modem", "listen", "voice"):
        out_mode = "modem"
    bed_raw = (bed_variant or "").strip() or None
    params = GreetingMixParams(
        intro_mode=(intro_mode or "none").strip().lower() or "none",
        intro_variant=(intro_variant or "tesla").strip() or "tesla",
        intro_sec=_form_float(intro_sec, 2.2),
        crossfade_ms=_form_int(crossfade_ms, 380),
        voice_bed_db=_form_float(voice_bed_db, -18.0),
        voice_mix_gain_db=_form_float(voice_mix_gain_db, 0.0),
        track_duck_db=_form_float(track_duck_db, 0.0),
        music_offset_sec=_form_float(music_offset_sec, 0.0),
        bed_variant=bed_raw,
        sample_rate=_form_int(sample_rate, 11025),
        sample_width=_form_int(sample_width, 2),
        tts_voice_gain_db=_form_float(tts_voice_gain_db, -6.0),
        append_beep=str(append_beep or "1").strip().lower() in ("1", "true", "yes", "on"),
        beep_gap_ms=_form_int(beep_gap_ms, 500),
        output=out_mode,  # type: ignore[arg-type]
    )

    work = Path(tempfile.mkdtemp(prefix="vg-greeting-mix-"))
    tts_path = work / "tts.mp3"
    intro_path: Optional[Path] = None
    beep_path: Optional[Path] = None
    out_path = work / ("listen.wav" if out_mode in ("listen", "voice") else "modem.wav")

    try:
        speak_text = _wrap_edge_ssml_if_needed(speak, voice_id)
        communicate = edge_tts.Communicate(
            speak_text,
            voice_id,
            rate=(rate or "+0%").strip() or "+0%",
            pitch=(pitch or "+0Hz").strip() or "+0Hz",
        )
        await communicate.save(str(tts_path))
        if not tts_path.is_file() or tts_path.stat().st_size < 32:
            raise HTTPException(status_code=422, detail="TTS vide")

        if intro_file is not None and intro_file.filename:
            suffix = Path(intro_file.filename).suffix or ".wav"
            intro_path = work / f"intro{suffix}"
            intro_path.write_bytes(await intro_file.read())
        if beep_file is not None and beep_file.filename:
            suffix = Path(beep_file.filename).suffix or ".wav"
            beep_path = work / f"beep{suffix}"
            beep_path.write_bytes(await beep_file.read())

        await asyncio.to_thread(
            build_greeting_mix_from_tts_source,
            tts_path,
            out_path,
            params=params,
            intro_path=intro_path,
            beep_path=beep_path,
        )
        data = out_path.read_bytes()
        if not data:
            raise HTTPException(status_code=422, detail="Mix vide")
        logger.info(
            "greeting-mix OK mode={} output={} ({} octets)",
            params.intro_mode,
            out_mode,
            len(data),
        )
        return Response(content=data, media_type="audio/wav")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("greeting-mix echoue: {}", exc)
        raise HTTPException(status_code=422, detail=f"Mix impossible: {exc}") from exc
    finally:
        try:
            import shutil

            shutil.rmtree(work, ignore_errors=True)
        except OSError:
            pass
