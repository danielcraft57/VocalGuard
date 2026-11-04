"""
Routes API Base de connaissances (intents + predict + prefetch voix).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel, Field

from backend.database import database as db_module
from backend.services import intent_repository as intent_repo
from backend.services import kb_chat_store
from backend.services.kb_tts_prefetch import prefetch_intent_voices, preview_tts_audio
from backend.voice.node15_voice_client import Node15VoiceClient
from backend.voice.response_picker import (
    apply_recent_tag_penalty,
    variant_wav_basename,
)
from backend.voice.dialogue_persona import resolve_dialogue_reply
from backend.voice.stt_remote import check_stt_service_health

router = APIRouter(prefix="/kb", tags=["kb"])


class IntentPredictBody(BaseModel):
    """Corps predict."""

    text: str = Field(..., min_length=1)
    top_k: int = Field(default=8, ge=1, le=32)
    profile: Optional[str] = Field(
        default=None,
        description="inbound | outbound_commercial (defaut inbound)",
    )


class IntentCreateBody(BaseModel):
    """Creation d'un intent KB."""

    tag: str = Field(..., min_length=2, max_length=80)
    patterns: List[str] = Field(default_factory=list)
    responses: List[str] = Field(default_factory=list)
    priority: int = Field(default=10, ge=0, le=100)
    enabled: bool = True
    action: Optional[str] = None
    niveau: int = Field(default=1, ge=1, le=9)
    profile: Optional[str] = Field(
        default=None,
        description="inbound | outbound_commercial",
    )


class IntentUpdateBody(BaseModel):
    """Mise a jour partielle d'un intent."""

    responses: Optional[List[str]] = None
    patterns: Optional[List[str]] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    action: Optional[str] = None
    clear_action: bool = False


class ChatBody(BaseModel):
    """Message utilisateur pour le tchat KB."""

    text: str = Field(..., min_length=1)
    top_k: int = Field(default=8, ge=1, le=32)
    recent_replies: List[str] = Field(default_factory=list)
    recent_tags: List[str] = Field(default_factory=list)
    recent_user_texts: List[str] = Field(default_factory=list)
    profile: Optional[str] = Field(
        default=None,
        description="inbound | outbound_commercial (defaut inbound)",
    )


class PrefetchBody(BaseModel):
    """Regeneration des voix."""

    force: bool = False
    tags: Optional[List[str]] = None
    profile: Optional[str] = None
    tts_provider: Optional[str] = None
    edge_tts_voice: Optional[str] = None
    edge_tts_rate: Optional[str] = None
    edge_tts_pitch: Optional[str] = None
    tts_voice_gain_db: Optional[float] = None
    elevenlabs_voice_id: Optional[str] = None


class VoicePreviewBody(BaseModel):
    """Apercu TTS d'une seule phrase (sans regenerer le catalogue)."""

    text: str = Field(..., min_length=1, max_length=4000)
    tts_provider: Optional[str] = None
    edge_tts_voice: Optional[str] = None
    edge_tts_rate: Optional[str] = None
    edge_tts_pitch: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    # Optionnel : ecrit aussi le WAV modem pour ce tag/index.
    save_tag: Optional[str] = None
    save_index: Optional[int] = Field(default=None, ge=0, le=32)
    profile: Optional[str] = None
    tts_voice_gain_db: Optional[float] = None


class ChatSessionUpsertBody(BaseModel):
    """Session tchatche complete (upsert)."""

    id: str = Field(..., min_length=2, max_length=80)
    title: str = Field(default="Conversation", max_length=255)
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    recentReplies: List[str] = Field(default_factory=list)
    recentTags: List[str] = Field(default_factory=list)
    recentUserTexts: List[str] = Field(default_factory=list)
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class ChatImportBody(BaseModel):
    """Import lot (migration localStorage)."""

    sessions: List[Dict[str, Any]] = Field(default_factory=list)


def _db():
    if db_module.SessionLocal is None:
        raise HTTPException(status_code=503, detail="Base de donnees non initialisee")
    return db_module.SessionLocal()


def _base_path(request: Request) -> Path:
    """Racine projet depuis la config app."""
    config = getattr(request.app.state, "config", None)
    if config and getattr(config, "base_path", None):
        return Path(config.base_path)
    return Path(".")


def _safe_wav_path(base: Path, basename: str) -> Path:
    """
    Resolut un WAV sous ivr_wav/ sans path traversal.

    @param base Racine projet.
    @param basename Nom sans extension (ex. kb_prise_rdv).
    @returns Chemin absolu attendu.
    @raises HTTPException Si nom invalide.
    """
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


def _enrich_has_wav(base: Path, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ajoute has_wav sur chaque intent."""
    for item in items:
        basename = item.get("wav_basename") or f"kb_{item.get('tag')}"
        try:
            item["has_wav"] = _safe_wav_path(base, str(basename)).is_file()
        except HTTPException:
            item["has_wav"] = False
    return items


@router.get("/intents")
async def get_intents(
    request: Request,
    enabled_only: bool = False,
    profile: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Liste les intents (patterns + responses) depuis Postgres.

    @param enabled_only Filtre enabled.
    @param profile inbound | outbound_commercial (None = tous).
    """
    db = _db()
    try:
        intent_repo.ensure_seeded(db, _base_path(request))
        prof = (profile or "").strip().lower() or None
        items = intent_repo.list_intents_detailed(
            db, enabled_only=enabled_only, profile=prof
        )
        items = _enrich_has_wav(_base_path(request), items)
        return {"intents": items, "count": len(items), "profile": prof}
    finally:
        db.close()


@router.get("/conversation-status")
async def conversation_status(request: Request) -> Dict[str, Any]:
    """
    Etat de readiness du mode conversation (STT node15 + intents + voix).

    Utilise par l'UI settings pour afficher un statut produit, pas un bandeau
    "mode test".

    @param request Contexte FastAPI (config + base_path).
    @returns Dict ready / stt / comptes intents et WAV.
    """
    config = getattr(request.app.state, "config", None)
    stt_url = (getattr(config, "stt_service_url", None) or "").strip() if config else ""
    stt_configured = bool(stt_url)
    stt_ok = False
    stt_detail: Optional[str] = None
    if stt_configured:
        stt_ok = await check_stt_service_health(stt_url, timeout_sec=2.5)
        if not stt_ok:
            client = Node15VoiceClient(
                stt_url,
                token=getattr(config, "stt_internal_token", None) if config else None,
                timeout_sec=5.0,
            )
            health = await client.health()
            stt_detail = str(health.get("detail") or health.get("status") or "injoignable")
    else:
        stt_detail = "STT_SERVICE_URL non configure"

    intents_enabled = 0
    voices_ready = 0
    db = _db()
    try:
        intent_repo.ensure_seeded(db, _base_path(request))
        items = intent_repo.list_intents_detailed(db, enabled_only=True)
        items = _enrich_has_wav(_base_path(request), items)
        intents_enabled = len(items)
        voices_ready = sum(1 for item in items if item.get("has_wav"))
    finally:
        db.close()

    # STT obligatoire ; voix prechargees recommandees (sinon TTS a la volee).
    ready = stt_ok and intents_enabled > 0
    voices_complete = intents_enabled > 0 and voices_ready >= intents_enabled

    from backend.voice.qdrant_intents import (
        COLLECTION_INBOUND,
        COLLECTION_OUTBOUND_COMMERCIAL,
        fetch_all_qdrant_status,
        fetch_qdrant_status,
    )

    qdrant_all = fetch_all_qdrant_status()
    qdrant = fetch_qdrant_status(collection=COLLECTION_INBOUND)
    q_out = qdrant_all.get("outbound_commercial") or {}

    return {
        "ready": ready,
        "stt_configured": stt_configured,
        "stt_ok": stt_ok,
        "stt_detail": stt_detail,
        "intents_enabled": intents_enabled,
        "voices_ready": voices_ready,
        "voices_complete": voices_complete,
        "qdrant_configured": bool(qdrant.get("configured")),
        "qdrant_ok": bool(qdrant.get("ok")),
        "qdrant_url": qdrant.get("url"),
        "qdrant_points": int(qdrant.get("points_count") or 0),
        "qdrant_collection": qdrant.get("collection") or COLLECTION_INBOUND,
        "qdrant_detail": qdrant.get("detail"),
        "qdrant_points_outbound": int(q_out.get("points_count") or 0),
        "qdrant_ok_outbound": bool(q_out.get("ok")),
        "qdrant_collection_outbound": q_out.get("collection")
        or COLLECTION_OUTBOUND_COMMERCIAL,
        "vector_engine": (
            "qdrant"
            if qdrant.get("ok")
            else ("pgvector" if qdrant.get("configured") else "local")
        ),
    }


@router.get("/intents/{tag}")
async def get_intent(tag: str, request: Request) -> Dict[str, Any]:
    """Detail d'un intent par tag."""
    db = _db()
    try:
        intent_repo.ensure_seeded(db, _base_path(request))
        intent = intent_repo.get_intent_by_tag(db, tag)
        if intent is None:
            raise HTTPException(status_code=404, detail=f"Intent inconnu: {tag}")
        return {
            "id": intent.id,
            "tag": intent.tag,
            "source": intent.source,
            "niveau": intent.niveau,
            "enabled": intent.enabled,
            "priority": intent.priority,
            "wav_basename": intent.wav_basename,
            "action": intent.action,
            "patterns": [p.pattern for p in intent.patterns],
            "responses": [r.text for r in sorted(intent.responses, key=lambda x: x.position)],
        }
    finally:
        db.close()


@router.get("/intents/{tag}/voice")
async def listen_intent_voice(tag: str, request: Request) -> FileResponse:
    """
    Sert le WAV modem cache d'un intent (ecoute KB).

    @param tag Tag intent.
    @returns audio/wav.
    """
    db = _db()
    try:
        intent_repo.ensure_seeded(db, _base_path(request))
        intent = intent_repo.get_intent_by_tag(db, tag)
        if intent is None:
            raise HTTPException(status_code=404, detail=f"Intent inconnu: {tag}")
        basename = intent.wav_basename or f"kb_{tag}"
        path = _safe_wav_path(_base_path(request), basename)
        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail="WAV absent — regenerer les voix depuis /kb",
            )
        return FileResponse(
            path=str(path),
            media_type="audio/wav",
            filename=f"{basename}.wav",
        )
    finally:
        db.close()


@router.post("/intents")
async def create_intent(body: IntentCreateBody, request: Request) -> Dict[str, Any]:
    """
    Ajoute un intent (tag unique, patterns, reponses).

    @param body Tag + patterns + responses.
    @returns Intent cree.
    """
    db = _db()
    try:
        intent_repo.ensure_seeded(db, _base_path(request))
        try:
            created = intent_repo.create_intent(
                db,
                tag=body.tag,
                patterns=body.patterns,
                responses=body.responses,
                priority=body.priority,
                enabled=body.enabled,
                action=body.action,
                niveau=body.niveau,
                source="kb",
                profile=(body.profile or "inbound"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _enrich_has_wav(_base_path(request), [created])[0]
    finally:
        db.close()


@router.patch("/intents/{tag}")
async def patch_intent(tag: str, body: IntentUpdateBody, request: Request) -> Dict[str, Any]:
    """Met a jour responses / patterns / flags / action."""
    db = _db()
    try:
        updated = intent_repo.update_intent_response(
            db,
            tag,
            responses=body.responses,
            patterns=body.patterns,
            enabled=body.enabled,
            priority=body.priority,
            action=body.action,
            clear_action=body.clear_action,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Intent inconnu: {tag}")
        return _enrich_has_wav(_base_path(request), [updated])[0]
    finally:
        db.close()


@router.delete("/intents/{tag}")
async def delete_intent(tag: str) -> Dict[str, Any]:
    """
    Supprime un intent et ses patterns / embeddings.

    @param tag Tag a supprimer.
    """
    db = _db()
    try:
        ok = intent_repo.delete_intent(db, tag)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Intent inconnu: {tag}")
        return {"deleted": True, "tag": tag}
    finally:
        db.close()


@router.delete("/profiles/{profile}/intents")
async def wipe_profile_intents(profile: str) -> Dict[str, Any]:
    """
    Supprime tous les intents d'un profil (entrant ou commercial).

    @param profile inbound | outbound_commercial.
    @returns Compteur de suppressions.
    """
    prof = (profile or "").strip().lower()
    if prof not in ("inbound", "outbound_commercial"):
        raise HTTPException(
            status_code=400,
            detail="profile doit etre inbound ou outbound_commercial",
        )
    db = _db()
    try:
        n = intent_repo.delete_intents_by_profile(db, prof)
        return {"deleted": n, "profile": prof}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        db.close()


@router.post("/chat")
async def kb_chat(body: ChatBody, request: Request) -> Dict[str, Any]:
    """
    Tchat KB : predict + dialogue persona (contexte, patience, anti-boucle).

    @param body Message + historiques replies / tags / textes user.
    @returns reply, tag, score, mood, persona_reason, top_predictions.
    """
    preds: List[Dict[str, Any]] = []
    source = "local"

    from backend.voice.dialogue_persona import (
        predict_text_for_intent,
        reshape_predictions,
    )

    predict_text = predict_text_for_intent(body.text, body.recent_tags)

    # Tchat UI : predict local (Qdrant/pgvector/python). node15 STT reste pour le telephone.
    db = _db()
    try:
        intent_repo.ensure_seeded(db, _base_path(request))
        preds, engine = intent_repo.predict_intent_scores_detailed(
            db, predict_text, top_k=body.top_k, profile=body.profile
        )
        source = engine

        raw_preds = list(preds)
        preds = apply_recent_tag_penalty(preds, body.recent_tags)

        if not preds:
            return {
                "reply": "Desole, je n'ai pas compris. Reformulez ou demandez de l'aide.",
                "tag": None,
                "score": 0.0,
                "action": None,
                "response_index": -1,
                "wav_basename": None,
                "top_predictions": [],
                "raw_predictions": [],
                "mood": None,
                "persona_reason": None,
                "source": source,
            }

        reshaped = reshape_predictions(
            preds, recent_tags=body.recent_tags, user_text=body.text
        )
        peek_tag = str(reshaped[0]["tag"]) if reshaped else ""
        intent = intent_repo.get_intent_by_tag(db, peek_tag) if peek_tag else None
        catalog: List[str] = []
        action = None
        if intent is not None:
            action = intent.action
            catalog = [r.text for r in sorted(intent.responses, key=lambda x: x.position)]

        resolved = resolve_dialogue_reply(
            user_text=body.text,
            predictions=preds,
            recent_tags=body.recent_tags,
            recent_replies=body.recent_replies,
            recent_user_texts=body.recent_user_texts,
            catalog_responses=catalog,
        )
        tag = resolved.get("tag")
        score = float(resolved.get("score") or 0.0)
        reply = str(resolved.get("reply") or "")
        response_index = int(
            resolved.get("response_index")
            if resolved.get("response_index") is not None
            else -1
        )
        wav_basename = None
        if tag:
            if response_index >= 0:
                wav_basename = variant_wav_basename(str(tag), response_index)
            elif intent is not None and intent.tag == tag:
                wav_basename = intent.wav_basename or f"kb_{tag}"
            else:
                wav_basename = f"kb_{tag}"

        if tag and (intent is None or intent.tag != tag):
            intent2 = intent_repo.get_intent_by_tag(db, str(tag))
            action = intent2.action if intent2 is not None else action

        if resolved.get("action"):
            action = resolved.get("action")

        return {
            "reply": reply,
            "tag": tag,
            "score": score,
            "action": action,
            "response_index": response_index,
            "wav_basename": wav_basename,
            "top_predictions": resolved.get("top_predictions") or [],
            "raw_predictions": raw_preds,
            "mood": resolved.get("mood"),
            "persona_reason": resolved.get("persona_reason"),
            "source": source,
        }
    finally:
        db.close()


@router.post("/intent-predict")
async def intent_predict(body: IntentPredictBody, request: Request) -> Dict[str, Any]:
    """
    Predict intents (local Qdrant/pgvector/python ; node15 optionnel).
    """
    config = getattr(request.app.state, "config", None)
    stt_url = getattr(config, "stt_service_url", None) if config else None
    token = getattr(config, "stt_internal_token", None) if config else None

    db = _db()
    try:
        intent_repo.ensure_seeded(db, _base_path(request))
        preds, engine = intent_repo.predict_intent_scores_detailed(
            db, body.text, top_k=body.top_k, profile=body.profile
        )
    finally:
        db.close()

    if stt_url:
        client = Node15VoiceClient(stt_url, token=token, timeout_sec=0.8)
        try:
            remote = await asyncio.wait_for(
                client.intent_predict(body.text, top_k=body.top_k),
                timeout=0.8,
            )
            if remote:
                return {"top_predictions": remote, "source": "node15"}
        except Exception as exc:
            logger.debug("Predict node15 ignore ({})", exc)

    return {"top_predictions": preds, "source": engine}

@router.post("/voices/regenerate")
async def regenerate_voices(body: PrefetchBody, request: Request) -> Dict[str, Any]:
    """
    Regenerere les WAV modem des intents (params voix d'accueil).
    """
    config = getattr(request.app.state, "config", None)
    call_manager = getattr(request.app.state, "call_manager", None)
    if config is None:
        raise HTTPException(status_code=503, detail="Config absente")
    synthesis = getattr(call_manager, "voice_synthesis", None) if call_manager else None
    if synthesis is None:
        from backend.voice.synthesis import VoiceSynthesis

        synthesis = VoiceSynthesis(config)
        await synthesis.initialize()

    db = _db()
    try:
        intent_repo.ensure_seeded(db, _base_path(request))
        result = await prefetch_intent_voices(
            db,
            config,
            synthesis,
            force=body.force,
            tags=body.tags,
            profile=body.profile,
            tts_provider=body.tts_provider,
            edge_tts_voice=body.edge_tts_voice,
            edge_tts_rate=body.edge_tts_rate,
            edge_tts_pitch=body.edge_tts_pitch,
            tts_voice_gain_db=body.tts_voice_gain_db,
            elevenlabs_voice_id=body.elevenlabs_voice_id,
        )
        return result
    finally:
        db.close()


@router.post("/voices/preview")
async def preview_voice(body: VoicePreviewBody, request: Request):
    """
    Apercu TTS d'une phrase (sans regenerer tout le catalogue).

    Si ``save_tag`` + ``save_index`` : ecrit uniquement le WAV de cette variante.
    """
    from fastapi.responses import Response

    from backend.services.kb_tts_prefetch import _write_modem_wav_from_mp3
    from backend.voice.ivr_cache import IvrAudioCache, ivr_content_hash
    from backend.voice.modem_profile import resolve_profile_from_config
    from backend.voice.response_picker import variant_wav_basename
    from backend.voice.synthesis import VoiceSynthesis

    config = getattr(request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=503, detail="Config absente")

    try:
        audio, media_type = await preview_tts_audio(
            config,
            body.text,
            tts_provider=body.tts_provider,
            edge_tts_voice=body.edge_tts_voice,
            edge_tts_rate=body.edge_tts_rate,
            edge_tts_pitch=body.edge_tts_pitch,
            elevenlabs_voice_id=body.elevenlabs_voice_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    saved = False
    if body.save_tag and body.save_index is not None:
        call_manager = getattr(request.app.state, "call_manager", None)
        synthesis = getattr(call_manager, "voice_synthesis", None) if call_manager else None
        if synthesis is None:
            synthesis = VoiceSynthesis(config)
            await synthesis.initialize()
        db = _db()
        try:
            intent = intent_repo.get_intent_by_tag(db, body.save_tag)
            if intent is not None:
                custom_base = getattr(intent, "wav_basename", None)
                basename = variant_wav_basename(
                    body.save_tag,
                    int(body.save_index),
                    wav_basename=str(custom_base) if custom_base else None,
                )
                cache = IvrAudioCache(config, synthesis)
                modem_profile = resolve_profile_from_config(config)
                provider = (body.tts_provider or "edge").strip().lower()
                voice = (body.edge_tts_voice or "edge").strip()
                gain = (
                    float(body.tts_voice_gain_db)
                    if body.tts_voice_gain_db is not None
                    else float(getattr(config, "edge_tts_voice_gain_db", -6.0) or -6.0)
                )
                h = ivr_content_hash(
                    body.text.strip(),
                    provider,
                    voice,
                    body.edge_tts_rate or "",
                    body.edge_tts_pitch or "",
                    gain,
                    profile_sample_rate=modem_profile.sample_rate,
                    profile_sample_width=modem_profile.sample_width,
                )
                await _write_modem_wav_from_mp3(
                    audio_bytes=audio,
                    basename=basename,
                    cache=cache,
                    modem_profile=modem_profile,
                    meta={
                        "hash": h,
                        "text": body.text.strip(),
                        "tag": body.save_tag,
                        "variant": int(body.save_index),
                        "engine": f"{provider}-preview",
                    },
                )
                saved = True
        finally:
            db.close()

    ext = "mp3" if "mpeg" in media_type else "wav"
    return Response(
        content=audio,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "X-VG-Saved": "1" if saved else "0",
            "Content-Disposition": f'inline; filename="kb_preview.{ext}"',
        },
    )


@router.post("/seed")
async def seed_intents(request: Request, replace: bool = False) -> Dict[str, Any]:
    """
    Rejoue le seed catalogue (one-shot ou replace).
    """
    db = _db()
    try:
        path = intent_repo.default_seed_path(_base_path(request))
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"Catalogue introuvable: {path}")
        catalog = intent_repo.load_seed_catalog(path)
        n = intent_repo.seed_intents_from_catalog(db, catalog, replace=replace)
        return {"seeded": n, "replace": replace, "path": str(path)}
    finally:
        db.close()


@router.get("/chats")
async def list_chats(limit: int = 30) -> Dict[str, Any]:
    """
    Liste les sessions tchatche en base.

    @param limit Nombre max.
    """
    db = _db()
    try:
        items = kb_chat_store.list_sessions(db, limit=limit)
        return {"sessions": items, "count": len(items)}
    finally:
        db.close()


@router.get("/chats/{session_id}")
async def get_chat(session_id: str) -> Dict[str, Any]:
    """Detail d'une session tchatche."""
    db = _db()
    try:
        row = kb_chat_store.get_session(db, session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Session introuvable")
        return row
    finally:
        db.close()


@router.put("/chats/{session_id}")
async def put_chat(session_id: str, body: ChatSessionUpsertBody) -> Dict[str, Any]:
    """
    Cree / met a jour une session (reprise possible).

    @param session_id Doit matcher body.id.
    """
    if body.id.strip() != session_id.strip():
        raise HTTPException(status_code=400, detail="id URL != body.id")
    db = _db()
    try:
        try:
            return kb_chat_store.upsert_session(db, body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        db.close()


@router.delete("/chats/{session_id}")
async def delete_chat(session_id: str) -> Dict[str, Any]:
    """Supprime une session tchatche."""
    db = _db()
    try:
        ok = kb_chat_store.delete_session(db, session_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Session introuvable")
        return {"deleted": True, "id": session_id}
    finally:
        db.close()


@router.post("/chats/import")
async def import_chats(body: ChatImportBody) -> Dict[str, Any]:
    """
    Importe un lot de sessions (ex. migration depuis localStorage).

    @param body sessions[].
    """
    db = _db()
    try:
        n = kb_chat_store.import_sessions(db, body.sessions or [])
        return {"imported": n}
    finally:
        db.close()
