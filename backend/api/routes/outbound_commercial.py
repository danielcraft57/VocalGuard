"""
Routes API appel commercial sortant (co-pilote top-5 + 5 phrases).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel, Field

from backend.core.events import Event, EventType, event_bus
from backend.core.outgoing_session_registry import outgoing_sessions
from backend.database import database as db_module
from backend.services import intent_repository as intent_repo
from backend.services import outbound_commercial_engine as commercial
from backend.services.kb_tts_prefetch import prefetch_intent_voices
from backend.voice.elevenlabs_client import ELEVENLABS_VOICE_MATILDA
from backend.voice.qdrant_intents import PROFILE_OUTBOUND_COMMERCIAL
from backend.voice.synthesis import VoiceSynthesis

router = APIRouter(prefix="/kb/outbound-commercial", tags=["kb-outbound-commercial"])


class SuggestBody(BaseModel):
    """Texte prospect / STT pour predict top-5."""

    text: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=8)
    call_id: Optional[int] = None


class PhrasesBody(BaseModel):
    """Choix d'un intent parmi le top-5."""

    tag: str = Field(..., min_length=2, max_length=100)


class ChooseBody(BaseModel):
    """Choix final phrase + lecture WAV optionnelle sur la ligne."""

    tag: str = Field(..., min_length=2, max_length=100)
    variant_index: int = Field(..., ge=0, le=4)
    call_id: Optional[int] = None
    play: bool = True


class PrefetchOutboundBody(BaseModel):
    """Regeneration voix sortantes."""

    force: bool = False
    tags: Optional[list[str]] = None
    tts_provider: Optional[str] = Field(
        default="elevenlabs",
        description="edge | elevenlabs (defaut elevenlabs / Matilda).",
    )
    elevenlabs_voice_id: Optional[str] = Field(
        default=ELEVENLABS_VOICE_MATILDA,
        description="Voix ElevenLabs (defaut Matilda).",
    )


class PredictOutboundBody(BaseModel):
    """Predict commercial (Postgres node14 + Qdrant node15)."""

    text: str = Field(default="", description="Parole prospect STT.")
    top_k: int = Field(default=8, ge=1, le=32)
    recent_tags: list[str] = Field(default_factory=list)
    recent_replies: list[str] = Field(default_factory=list)
    force_tag: Optional[str] = Field(default=None, max_length=100)
    variant_index: Optional[int] = Field(default=None, ge=0, le=4)


def _db():
    if db_module.SessionLocal is None:
        raise HTTPException(status_code=503, detail="Base de donnees non initialisee")
    return db_module.SessionLocal()


def _config(request: Request):
    """
    Config app : prefer call_manager, sinon app.state.config (API seule / simulateur).
    """
    cm = getattr(request.app.state, "call_manager", None)
    if cm is not None and getattr(cm, "config", None) is not None:
        return cm.config
    cfg = getattr(request.app.state, "config", None)
    if cfg is not None:
        return cfg
    raise HTTPException(status_code=503, detail="Configuration indisponible")


def _base_path(request: Request) -> Path:
    """Racine projet depuis la config."""
    config = _config(request)
    return Path(getattr(config, "base_path", None) or ".")


def _safe_wav_path(base: Path, basename: str) -> Path:
    """WAV sous ivr_wav/ sans path traversal."""
    name = (basename or "").strip()
    if not name or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Basename invalide")
    if not all(c.isalnum() or c in ("_", "-") for c in name):
        raise HTTPException(status_code=400, detail="Basename invalide")
    ivr = (base / "ivr_wav").resolve()
    path = (ivr / f"{name}.wav").resolve()
    if not str(path).startswith(str(ivr)):
        raise HTTPException(status_code=400, detail="Chemin refuse")
    return path


@router.get("/studio-config")
async def studio_desktop_config(request: Request) -> Dict[str, Any]:
    """
    Config STT pour le client bureau Commercial Studio (LAN).

    Renvoie le meme token que node14 utilise deja pour parler a node15 (Whisper).
    Reservé au reseau local VocalGuard ; ne pas exposer sur Internet.

    @returns stt_url, stt_token (peut etre vide si non configure).
    """
    config = _config(request)
    stt_url = (getattr(config, "stt_service_url", None) or "http://node15.lan:8100").strip()
    token = (getattr(config, "stt_internal_token", None) or "").strip()
    return {
        "stt_url": stt_url.rstrip("/"),
        "stt_token": token,
        "hint": (
            "Token HTTP interne node15 (Whisper). "
            "Identique a STT_INTERNAL_TOKEN sur node14 et node15."
        ),
    }


@router.post("/predict")
async def predict_outbound_commercial(
    body: PredictOutboundBody,
    request: Request,
) -> Dict[str, Any]:
    """
    Predict intent commercial : Postgres local + vecteurs Qdrant (node15).

    Utilise par Commercial Studio apres STT Whisper sur node15.

    @param body Texte + historique dialogue.
    @returns Tag, phrase, wav_basename, engine (qdrant).
    """
    db = _db()
    try:
        return commercial.predict_outbound_reply(
            db,
            body.text,
            top_k=body.top_k,
            recent_tags=body.recent_tags,
            recent_replies=body.recent_replies,
            force_tag=body.force_tag,
            variant_index=body.variant_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        db.close()


@router.get("/voice/{basename}")
async def listen_commercial_voice(basename: str, request: Request) -> FileResponse:
    """
    Streame un WAV commercial prefetch (HP navigateur / simulateur).

    @param basename Ex. out_kb_out_objection_prix_v2 (sans .wav).
    """
    path = _safe_wav_path(_base_path(request), basename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="WAV commercial introuvable")
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=f"{basename}.wav",
        headers={"Cache-Control": "private, max-age=120"},
    )


@router.post("/seed")
async def seed_outbound(request: Request, replace: bool = False) -> Dict[str, Any]:
    """
    Importe le seed ``outbound_commercial_v1.json``.

    @param replace Si True, recree les tags existants.
    """
    config = _config(request)
    path = intent_repo.outbound_seed_path(Path(config.base_path or "."))
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Seed introuvable: {path}")
    db = _db()
    try:
        catalog = intent_repo.load_seed_catalog(path)
        n = intent_repo.seed_intents_from_catalog(db, catalog, replace=replace)
        return {
            "ok": True,
            "inserted": n,
            "profile": PROFILE_OUTBOUND_COMMERCIAL,
            "path": str(path),
        }
    finally:
        db.close()


@router.get("/presentation")
async def get_presentation(request: Request) -> Dict[str, Any]:
    """Cinq formulations d'ouverture (avant / pendant composition)."""
    config = _config(request)
    db = _db()
    try:
        return commercial.presentation_phrases(db, config)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        db.close()


@router.post("/suggest")
async def suggest(body: SuggestBody, request: Request) -> Dict[str, Any]:
    """
    Predict top-5 intents commerciaux + event WS si call_id.
    """
    config = _config(request)
    db = _db()
    try:
        result = commercial.suggest_top_intents(
            db, body.text, config, top_k=body.top_k
        )
        if body.call_id is not None:
            session = outgoing_sessions.get(body.call_id)
            if session is not None:
                session.commercial_suggestions = result.get("suggestions") or []
                session.commercial_selected_tag = None
                session.commercial_phrases = []
            await event_bus.publish(
                Event(
                    event_type=EventType.OUTBOUND_COMMERCIAL_SUGGESTIONS,
                    data={
                        "call_id": body.call_id,
                        **result,
                    },
                    source="outbound_commercial",
                )
            )
        return result
    finally:
        db.close()


@router.post("/phrases")
async def phrases(body: PhrasesBody, request: Request) -> Dict[str, Any]:
    """Apres choix intent : retourne les 5 formulations."""
    config = _config(request)
    db = _db()
    try:
        result = commercial.select_intent_phrases(db, body.tag, config)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        db.close()


@router.post("/choose")
async def choose(body: ChooseBody, request: Request) -> Dict[str, Any]:
    """
    Valide une phrase et joue le WAV sur la ligne si ``play`` et session active.
    """
    config = _config(request)
    db = _db()
    try:
        resolved = commercial.resolve_choice(
            db,
            config,
            tag=body.tag,
            variant_index=body.variant_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        db.close()

    played = False
    play_error: Optional[str] = None
    if body.play and body.call_id is not None:
        session = outgoing_sessions.get(body.call_id)
        cm = getattr(request.app.state, "call_manager", None)
        modem = getattr(cm, "modem", None) if cm else None
        if session is None:
            play_error = "Session sortante introuvable"
        elif modem is None:
            play_error = "Modem indisponible"
        else:
            wav_path = Path(resolved["wav_path"])
            try:
                # Pause micro / VTX uplink le temps de jouer le clip.
                session.play_lock = getattr(session, "play_lock", None) or asyncio.Lock()
                async with session.play_lock:
                    session.playing_wav = True
                    try:
                        ok = await modem.play_wav_via_serial(str(wav_path))
                        played = bool(ok)
                        if not played:
                            play_error = "Lecture WAV refusee par le modem"
                    finally:
                        session.playing_wav = False
            except Exception as exc:
                play_error = str(exc)
                logger.exception("Play WAV commercial: {}", exc)

        await event_bus.publish(
            Event(
                event_type=EventType.OUTBOUND_COMMERCIAL_PLAY,
                data={
                    "call_id": body.call_id,
                    "played": played,
                    "error": play_error,
                    **{k: v for k, v in resolved.items() if k != "wav_path"},
                },
                source="outbound_commercial",
            )
        )

    return {
        "ok": True,
        "played": played,
        "play_error": play_error,
        **{k: v for k, v in resolved.items() if k != "wav_path"},
    }


@router.post("/voices/regenerate")
async def regenerate_outbound_voices(
    body: PrefetchOutboundBody,
    request: Request,
) -> Dict[str, Any]:
    """Prefetch offline des WAV ``out_kb_*`` (ElevenLabs ou Edge)."""
    config = _config(request)
    cm = request.app.state.call_manager
    synthesis = getattr(cm, "voice_synthesis", None)
    if synthesis is None:
        synthesis = VoiceSynthesis(config)
        await synthesis.initialize()
    db = _db()
    try:
        intent_repo.ensure_seeded(
            db, Path(config.base_path or "."), profile=PROFILE_OUTBOUND_COMMERCIAL
        )
        stats = await prefetch_intent_voices(
            db,
            config,
            synthesis,
            force=body.force,
            tags=body.tags,
            profile=PROFILE_OUTBOUND_COMMERCIAL,
            tts_provider=body.tts_provider or "elevenlabs",
            elevenlabs_voice_id=body.elevenlabs_voice_id or ELEVENLABS_VOICE_MATILDA,
        )
        return {"ok": True, **stats}
    finally:
        db.close()
