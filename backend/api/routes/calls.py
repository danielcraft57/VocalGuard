"""
Routes API pour les appels.
Avec with_osint=1, la reputation OSINT est lue depuis la table phone_number_profiles (pas d'appel OSINT en direct).
"""

from __future__ import annotations

import asyncio
import time
import wave
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from typing import Literal, Optional

import httpx

from backend.voice.audio_utils import (
    has_alsa_capture_devices,
    pcm_s16le_16k_mono_to_u8_8k,
    pcm_s16le_rms,
    pcm_u8_8k_to_s16le_16k,
    write_stereo_u8_8k_wav,
)

from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel, Field

from backend.api.dependencies import get_block_service, get_call_repository, get_config, get_db
from backend.repositories.call_repository import CallRepository
from backend.api.models import CallResponse, CallListResponse, OsintReputationResponse
from backend.database.models import Call, PhoneNumberProfile
from backend.core.events import Event, EventType, event_bus
from backend.core.config import Config
from backend.core.outgoing_session_registry import (
    OutgoingCallSession,
    outgoing_sessions,
    session_broadcast_pcm,
    session_stop_mic_aplay,
)
from backend.osint.services import PhoneOsintService
from backend.services.block_service import BlockService


router = APIRouter()


class OutgoingCallStartRequest(BaseModel):
    """Payload pour demarrer un appel sortant modem."""

    phone_number: str = Field(..., min_length=1, max_length=32)


class OutgoingCallActionResponse(BaseModel):
    """Reponse simple des actions d appel sortant."""

    ok: bool
    call_id: int
    message: str


class DtmfRequest(BaseModel):
    """Payload pour envoi de touche DTMF."""

    digit: str = Field(..., min_length=1, max_length=1)


class CallTagUpdate(BaseModel):
    """Tag UI pour classer un appel / numero (metadonnees + liste blanche/noire si pertinent)."""

    tag: Literal["permitted", "restricted", "unknown", "blocked", "commercial", "none"]


class CallBulkDeleteRequest(BaseModel):
    """Suppression de plusieurs appels."""

    ids: list[int] = Field(..., min_length=1, max_length=500)


def _telephony_daemon_base(request: Request, config: Config) -> str:
    base = getattr(request.app.state, "telephony_daemon_url", None) or config.telephony_daemon_url
    return str(base).strip().rstrip("/")


def _should_proxy_outgoing_to_daemon(config: Config, request: Request) -> bool:
    """
    Le service vocalguard-telephony traite les routes sortantes en local : ne jamais proxifier.

    Sinon avec USE_TELEPHONY_DAEMON=1 dans .env du Pi, le daemon se rappelle en boucle via httpx
    jusqu'à OSError « Too many open files ».
    """
    if getattr(request.app.state, "is_vocalguard_telephony_daemon", False):
        return False
    return bool(config.use_telephony_daemon)


async def _proxy_outgoing_to_telephony(
    request: Request, config: Config, path: str, json_body: Optional[dict] = None
) -> OutgoingCallActionResponse:
    base = _telephony_daemon_base(request, config)
    url = f"{base}{path}"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=json_body if json_body is not None else {}, timeout=300.0)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Service telephony injoignable (verifier sur le Pi: "
                "`sudo systemctl status vocalguard-telephony` et TELEPHONY_DAEMON_URL dans .env). "
                f"Detail: {exc}"
            ),
        ) from exc
    try:
        data = r.json()
    except Exception:
        raise HTTPException(status_code=502, detail=(r.text or "Reponse telephony invalide")[:500])
    if r.status_code >= 400:
        if r.status_code == 405:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Le service indique par TELEPHONY_DAEMON_URL refuse le POST (405). "
                    "Verifiez l’URL (doit etre le daemon `backend.telephony_daemon.main`, port 8090 en general), "
                    "deployeez une version recente sur le Pi, ou en dev local sans modem mettez USE_TELEPHONY_DAEMON=0 "
                    "(sinon l’API proxifie encore vers une mauvaise cible)."
                ),
            )
        det = data.get("detail") if isinstance(data, dict) else data
        if isinstance(det, list):
            det = str(det)
        code = r.status_code if 400 <= r.status_code < 600 else 502
        raise HTTPException(status_code=code, detail=str(det or "Erreur telephony"))
    return OutgoingCallActionResponse(**data)


def _safe_recording_path(config: Config, audio_file: Optional[str]) -> Optional[Path]:
    if not audio_file or ".." in audio_file:
        return None
    norm = audio_file.replace("\\", "/").strip().lstrip("/")
    if not norm.startswith("recordings/"):
        return None
    base = Path(config.base_path).resolve() if config.base_path else Path.cwd().resolve()
    full = (base / norm).resolve()
    try:
        full.relative_to(base)
    except ValueError:
        return None
    return full if full.is_file() else None


def _try_unlink_recording(config: Config, audio_file: Optional[str]) -> None:
    p = _safe_recording_path(config, audio_file)
    if p and p.is_file():
        try:
            p.unlink()
        except OSError:
            pass


async def _publish_state(event_type: EventType, call_id: int, phone_number: str, **extra) -> None:
    """Publie un etat d'appel sortant sur le bus d'evenements realtime."""
    payload = {"call_id": call_id, "phone_number": phone_number}
    payload.update(extra)
    await event_bus.publish(
        Event(
            event_type=event_type,
            timestamp=datetime.utcnow(),
            data=payload,
            source="CallsRoute",
        )
    )


async def _publish_log(call_id: int, phone_number: str, message: str, level: str = "info") -> None:
    """Publie une ligne de journal pour la modale d'appel (WebSocket /ws/events)."""
    await event_bus.publish(
        Event(
            event_type=EventType.CALL_SESSION_LOG,
            timestamp=datetime.utcnow(),
            data={"call_id": call_id, "phone_number": phone_number, "message": message, "level": level},
            source="CallsRoute",
        )
    )


async def _run_outgoing_call_session(app, session: OutgoingCallSession) -> None:
    """Boucle de session sortante: dial, ALSA ou streaming VRX serie, STT, enregistrement WAV, cloture."""
    call_manager = getattr(app.state, "call_manager", None)
    if call_manager is None:
        return
    call_service = call_manager.call_service
    modem = call_manager.modem
    arecord_proc: Optional[asyncio.subprocess.Process] = None
    alsa_reader_task: Optional[asyncio.Task] = None
    finalize_completion = True
    end_reason = "hangup"
    end_error: Optional[str] = None
    serial_vrx_active = False
    base = Path(call_manager.config.base_path) if call_manager.config.base_path else Path(".")
    recordings_dir = base / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    wav_rel: Optional[str] = None
    use_alsa_live = has_alsa_capture_devices()
    stt_buffer = bytearray()
    stream_key = f"out_{session.call_id}"
    vosk_stream_ok = False
    STT_FEED_BYTES = 3200  # 100 ms PCM 16 kHz mono s16le — partiels VOSK plus fluides
    last_partial_sent: list[Optional[str]] = [None]

    async def _stt_flush_legacy(stt_buffer: bytearray) -> None:
        chunk_sz = 64000
        while len(stt_buffer) >= chunk_sz:
            pcm = bytes(stt_buffer[:chunk_sz])
            del stt_buffer[:chunk_sz]
            text = await call_manager.voice_recognition.transcribe(pcm, sample_rate=16000)
            text = (text or "").strip()
            if not text:
                continue
            session.transcript_parts.append(text)
            await _publish_log(session.call_id, session.phone_number, f"STT: {text}")
            await _publish_state(
                EventType.CALL_TRANSCRIPTION_PARTIAL,
                session.call_id,
                session.phone_number,
                text=text,
                live=False,
            )

    async def _feed_stt_stream(stt_buffer: bytearray) -> None:
        if vosk_stream_ok:
            while len(stt_buffer) >= STT_FEED_BYTES:
                pcm = bytes(stt_buffer[:STT_FEED_BYTES])
                del stt_buffer[:STT_FEED_BYTES]
                partial, segments = call_manager.voice_recognition.outgoing_stream_feed(stream_key, pcm)
                if partial and partial != last_partial_sent[0]:
                    last_partial_sent[0] = partial
                    await _publish_state(
                        EventType.CALL_TRANSCRIPTION_PARTIAL,
                        session.call_id,
                        session.phone_number,
                        text=partial,
                        live=True,
                    )
                for seg in segments:
                    session.transcript_parts.append(seg)
                    last_partial_sent[0] = None
                    await _publish_log(session.call_id, session.phone_number, f"STT: {seg}")
                    await _publish_state(
                        EventType.CALL_TRANSCRIPTION_PARTIAL,
                        session.call_id,
                        session.phone_number,
                        text=seg,
                        live=False,
                    )
        else:
            await _stt_flush_legacy(stt_buffer)

    alsa_raw = bytearray()
    serial_line_track = bytearray()
    serial_mic_track = bytearray()
    _SILENCE_U8 = 128

    def _append_line_chunk(chunk: bytes) -> None:
        n = len(chunk)
        if n <= 0:
            return
        serial_line_track.extend(chunk)
        serial_mic_track.extend(bytes([_SILENCE_U8]) * n)

    def _append_mic_uplink(u8: bytes) -> None:
        n = len(u8)
        if n <= 0:
            return
        serial_line_track.extend(bytes([_SILENCE_U8]) * n)
        serial_mic_track.extend(u8)

    async def _save_serial_stereo_wav() -> None:
        nonlocal wav_rel
        if wav_rel is not None:
            return
        if not serial_line_track and not serial_mic_track:
            return
        ts = int(time.time())
        wav_rel = f"recordings/call_out_{session.call_id}_{ts}.wav"
        wav_path = base / wav_rel
        write_stereo_u8_8k_wav(wav_path, bytes(serial_line_track), bytes(serial_mic_track))
        await call_service.set_audio_file(session.call_id, wav_rel)
        await _publish_log(
            session.call_id,
            session.phone_number,
            f"Enregistrement stéréo sauvegardé ({wav_rel})",
        )

    try:
        stt_allowed = {"ok": False}

        await _publish_log(session.call_id, session.phone_number, f"Composition vers {session.phone_number} (ATD)")

        async def _alsa_capture_loop() -> None:
            """Lit arecord en continu : ligne vers WebSocket des le decroche avant CONNECT ; STT seulement apres ligne OK."""
            idle_reads = 0
            proc = arecord_proc
            if proc is None:
                return
            while not session.stop_event.is_set():
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    idle_reads += 1
                    if idle_reads > 80:
                        await _publish_log(session.call_id, session.phone_number, "Fin flux arecord", "warn")
                        break
                    await asyncio.sleep(0.05)
                    continue
                idle_reads = 0
                alsa_raw.extend(chunk)
                await session_broadcast_pcm(session, chunk)
                if stt_allowed["ok"]:
                    stt_buffer.extend(chunk)
                    await _feed_stt_stream(stt_buffer)

        if use_alsa_live:
            try:
                arecord_proc = await asyncio.create_subprocess_exec(
                    "arecord",
                    "-D",
                    call_manager._alsa_record,
                    "-f",
                    "S16_LE",
                    "-r",
                    "16000",
                    "-c",
                    "1",
                    "-t",
                    "raw",
                    "-",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError:
                arecord_proc = None
                await _publish_log(session.call_id, session.phone_number, "arecord introuvable", "warn")

        if arecord_proc is not None:
            await _publish_log(
                session.call_id,
                session.phone_number,
                f"Audio live ALSA {call_manager._alsa_record} -> navigateur (des la composition); micro -> "
                f"{call_manager._alsa_play} ou file modem",
            )
            alsa_reader_task = asyncio.create_task(_alsa_capture_loop())

        dial_ok, raw = await modem.dial_number(session.phone_number)
        preview = (raw or "").replace("\r\n", " ")[:420]
        await _publish_log(session.call_id, session.phone_number, f"Reponse modem: {preview!r}")
        if not dial_ok:
            await _publish_log(session.call_id, session.phone_number, "Echec composition (pas OK/CONNECT)", "error")
            await call_service.miss_call(session.call_id)
            await _publish_state(
                EventType.CALL_OUTGOING_ENDED,
                session.call_id,
                session.phone_number,
                reason="dial_failed",
                modem_response=raw,
            )
            finalize_completion = False
            return
        await call_service.answer_call(session.call_id)
        await _publish_state(EventType.CALL_OUTGOING_CONNECTED, session.call_id, session.phone_number)
        await _publish_log(session.call_id, session.phone_number, "Ligne connectee")
        vosk_stream_ok = call_manager.voice_recognition.outgoing_stream_start(stream_key)
        stt_allowed["ok"] = True

        if arecord_proc is not None:
            while not session.stop_event.is_set():
                await asyncio.sleep(0.05)
        elif modem.supports_voice_serial:
            await _publish_log(
                session.call_id,
                session.phone_number,
                "Pas de capture ALSA: flux VRX (modem) -> WebSocket; micro -> VTX par rafales",
            )
            modem._outgoing_owns_serial = True
            ok = await modem.start_outgoing_vrx_stream(already_in_voice_mode=False)
            if not ok:
                await _publish_log(session.call_id, session.phone_number, "Echec ouverture VRX", "error")
                modem._outgoing_owns_serial = False
            else:
                serial_vrx_active = True
                mic_acc = bytearray()
                # ~400 ms a 16 kHz s16le — moins de bascules VRX<->VTX = moins de saccades
                MIC_BURST_BYTES = 12800
                MAX_MIC_BACKLOG = MIC_BURST_BYTES * 3
                # Seuil VAD : sous ce RMS, on jette le silence sans toucher au modem
                MIC_VAD_RMS = 450.0
                uplink_bursts = 0
                silence_drops = 0
                while not session.stop_event.is_set():
                    chunk = await modem.read_outgoing_vrx_chunk(1024)
                    if chunk:
                        _append_line_chunk(chunk)
                        pcm16 = pcm_u8_8k_to_s16le_16k(chunk)
                        await session_broadcast_pcm(session, pcm16)
                        stt_buffer.extend(pcm16)
                        await _feed_stt_stream(stt_buffer)
                    try:
                        while True:
                            mic_acc.extend(session.mic_modem_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        pass
                    if len(mic_acc) > MAX_MIC_BACKLOG:
                        # Garde la fin (parole recente), jette le trop-plein
                        del mic_acc[:-MIC_BURST_BYTES]
                    if len(mic_acc) >= MIC_BURST_BYTES:
                        burst = bytes(mic_acc[:MIC_BURST_BYTES])
                        del mic_acc[:MIC_BURST_BYTES]
                        rms = pcm_s16le_rms(burst)
                        if rms < MIC_VAD_RMS:
                            silence_drops += 1
                            # Silence : pas de VTX, on continue d'ecouter la ligne
                            continue
                        u8 = pcm_s16le_16k_mono_to_u8_8k(burst)
                        if u8:
                            _append_mic_uplink(u8)
                            ok_up = await modem.half_duplex_send_uplink_u8(u8)
                            uplink_bursts += 1
                            if uplink_bursts == 1 or uplink_bursts % 10 == 0:
                                await _publish_log(
                                    session.call_id,
                                    session.phone_number,
                                    f"Uplink VTX #{uplink_bursts} ({len(u8)} o, rms={rms:.0f}, ok={ok_up})",
                                )
                    if not chunk:
                        await asyncio.sleep(0.02)
                if mic_acc:
                    rms_tail = pcm_s16le_rms(bytes(mic_acc))
                    if rms_tail >= MIC_VAD_RMS:
                        u8_tail = pcm_s16le_16k_mono_to_u8_8k(bytes(mic_acc))
                        if u8_tail:
                            _append_mic_uplink(u8_tail)
                            await modem.half_duplex_send_uplink_u8(u8_tail)
                            uplink_bursts += 1
                    mic_acc.clear()
                await _publish_log(
                    session.call_id,
                    session.phone_number,
                    f"Fin session VRX: {uplink_bursts} rafales micro, {silence_drops} silences ignores",
                )
                await _save_serial_stereo_wav()
        else:
            await _publish_log(
                session.call_id,
                session.phone_number,
                "Fallback STT par enregistrements courts (pas ALSA ni voix serie)",
                "warn",
            )
            while not session.stop_event.is_set():
                audio_data = await call_manager._record_audio(duration=2, already_in_voice_mode=False)
                if not audio_data:
                    await asyncio.sleep(0.3)
                    continue
                text = await call_manager.voice_recognition.transcribe(audio_data, sample_rate=16000)
                text = (text or "").strip()
                if not text:
                    continue
                session.transcript_parts.append(text)
                await _publish_log(session.call_id, session.phone_number, f"STT: {text}")
                await _publish_state(
                    EventType.CALL_TRANSCRIPTION_PARTIAL,
                    session.call_id,
                    session.phone_number,
                    text=text,
                )
    except Exception as exc:
        end_reason = "runtime_error"
        end_error = str(exc)
        await _publish_log(session.call_id, session.phone_number, f"Erreur session: {exc}", "error")
    finally:
        session.stop_event.set()
        if alsa_reader_task is not None:
            try:
                await asyncio.wait_for(alsa_reader_task, timeout=8.0)
            except asyncio.TimeoutError:
                alsa_reader_task.cancel()
                try:
                    await alsa_reader_task
                except asyncio.CancelledError:
                    pass
        if arecord_proc is not None and arecord_proc.returncode is None:
            try:
                arecord_proc.terminate()
                await asyncio.wait_for(arecord_proc.wait(), timeout=2.0)
            except Exception:
                try:
                    arecord_proc.kill()
                except Exception:
                    pass
        if len(alsa_raw) > 0 and wav_rel is None:
            ts = int(time.time())
            wav_rel = f"recordings/call_out_{session.call_id}_{ts}.wav"
            wav_path = base / wav_rel
            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(bytes(alsa_raw))
            await call_service.set_audio_file(session.call_id, wav_rel)

        if serial_vrx_active:
            try:
                await modem.end_outgoing_vrx_stream()
            except Exception:
                pass
        modem._outgoing_owns_serial = False
        await session_stop_mic_aplay(session)
        try:
            await modem.hangup()
        except Exception:
            pass
        outgoing_sessions.pop(session.call_id, None)
        if not finalize_completion:
            return
        if call_manager and vosk_stream_ok:
            if len(stt_buffer) > 0:
                partial, segments = call_manager.voice_recognition.outgoing_stream_feed(stream_key, bytes(stt_buffer))
                stt_buffer.clear()
                if partial and partial != last_partial_sent[0]:
                    last_partial_sent[0] = partial
                    await _publish_state(
                        EventType.CALL_TRANSCRIPTION_PARTIAL,
                        session.call_id,
                        session.phone_number,
                        text=partial,
                        live=True,
                    )
                for seg in segments:
                    session.transcript_parts.append(seg)
                    last_partial_sent[0] = None
                    await _publish_log(session.call_id, session.phone_number, f"STT: {seg}")
                    await _publish_state(
                        EventType.CALL_TRANSCRIPTION_PARTIAL,
                        session.call_id,
                        session.phone_number,
                        text=seg,
                        live=False,
                    )
            rest = call_manager.voice_recognition.outgoing_stream_end(stream_key)
            if rest:
                session.transcript_parts.append(rest)
                await _publish_state(
                    EventType.CALL_TRANSCRIPTION_PARTIAL,
                    session.call_id,
                    session.phone_number,
                    text=rest,
                    live=False,
                )
        elif call_manager and len(stt_buffer) > 8000:
            tail = bytes(stt_buffer)
            text = await call_manager.voice_recognition.transcribe(tail, sample_rate=16000)
            text = (text or "").strip()
            if text:
                session.transcript_parts.append(text)
        duration = int(max(0, time.monotonic() - session.started_monotonic))
        final_text = " ".join(session.transcript_parts).strip() or None
        if final_text:
            await call_service.set_transcription_and_intent(session.call_id, transcription=final_text)
            await _publish_state(
                EventType.CALL_TRANSCRIPTION_FINAL,
                session.call_id,
                session.phone_number,
                text=final_text,
            )
        await call_service.complete_call(session.call_id, duration=duration)
        await _publish_state(
            EventType.CALL_OUTGOING_ENDED,
            session.call_id,
            session.phone_number,
            reason=end_reason,
            duration=duration,
            **({"error": end_error} if end_error else {}),
        )


def _profile_to_osint_response(profile: PhoneNumberProfile, phone_number: str) -> OsintReputationResponse:
    """
    Construit OsintReputationResponse a partir d'un PhoneNumberProfile (reputation + lieu + operateur).
    La reputation en base n'est remplie que par des sources externes (NumLookup, phoneinfoga).
    Si on a lieu/operateur (détection FR) mais pas de reputation, on renvoie "neutral" (non évaluée).
    """
    rep = (profile.reputation or "unknown").strip() or "unknown"
    if rep == "unknown" and (profile.region or profile.city or profile.operator):
        rep = "neutral"
    conf = profile.confidence
    if conf is not None:
        conf_float = float(conf) / 100.0
    else:
        conf_float = 0.0
    rec = "review"
    if profile.is_scam or profile.is_spam or profile.is_telemarketer:
        rec = "block"
    elif rep == "high":
        rec = "allow"
    elif rep == "neutral":
        rec = "review"
    return OsintReputationResponse(
        phone_number=phone_number,
        reputation=rep,
        is_spam=profile.is_spam or False,
        is_scam=profile.is_scam or False,
        is_commercial=profile.is_commercial or False,
        is_telemarketer=profile.is_telemarketer or False,
        confidence=conf_float,
        sources=["database"],
        recommendation=rec,
        city=profile.city or None,
        region=profile.region or None,
        operator=profile.operator or None,
    )


@router.get("/calls", response_model=CallListResponse)
async def get_calls(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = None,
    phone_number: Optional[str] = None,
    with_osint: bool = Query(False, description="Inclure la reputation OSINT depuis la base (rapide)"),
    call_repo: CallRepository = Depends(get_call_repository),
    db: Session = Depends(get_db),
):
    """
    Recupere la liste des appels.
    Avec with_osint=true, joint les profils OSINT deja en base (pas d'appel API OSINT).
    """
    filters = {}
    if status:
        filters["status"] = status
    if phone_number:
        filters["phone_number"] = phone_number

    total = call_repo.count(**filters)
    calls = call_repo.get_all(skip=skip, limit=limit, **filters)

    if not with_osint:
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "calls": [CallResponse.model_validate(call) for call in calls],
        }

    phones = list({c.phone_number for c in calls if c.phone_number})
    profile_by_phone: dict[str, PhoneNumberProfile] = {}
    if phones:
        rows = (
            db.query(PhoneNumberProfile)
            .filter(PhoneNumberProfile.phone_number.in_(phones))
            .order_by(PhoneNumberProfile.phone_number, desc(PhoneNumberProfile.last_checked_at))
            .all()
        )
        for p in rows:
            if p.phone_number not in profile_by_phone:
                profile_by_phone[p.phone_number] = p

    result_calls = []
    for call in calls:
        data = CallResponse.model_validate(call).model_dump()
        if call.phone_number and call.phone_number in profile_by_phone:
            data["osint"] = _profile_to_osint_response(profile_by_phone[call.phone_number], call.phone_number)
        else:
            data["osint"] = None
        result_calls.append(CallResponse(**data))

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "calls": result_calls,
    }


@router.post("/calls/bulk-delete")
async def bulk_delete_calls(
    body: CallBulkDeleteRequest,
    db: Session = Depends(get_db),
    config: Config = Depends(get_config),
):
    """Supprime plusieurs appels et leurs fichiers recordings/ associes."""
    repo = CallRepository(db)
    deleted = 0
    for cid in body.ids:
        c = repo.get_by_id(cid)
        if c:
            _try_unlink_recording(config, c.audio_file)
            if repo.delete(cid):
                deleted += 1
    return {"deleted": deleted}


@router.get("/calls/{call_id}/recording")
async def get_call_recording(
    call_id: int,
    call_repo: CallRepository = Depends(get_call_repository),
    config: Config = Depends(get_config),
):
    """Sert le fichier WAV d'un appel (chemin relatif securise sous recordings/)."""
    call = call_repo.get_by_id(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Appel non trouvé")
    path = _safe_recording_path(config, call.audio_file)
    if not path:
        raise HTTPException(status_code=404, detail="Enregistrement indisponible")
    return FileResponse(str(path), media_type="audio/wav", filename=path.name)


@router.get("/calls/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: int,
    with_osint: bool = Query(False, description="Joindre le profil OSINT en base si disponible"),
    call_repo: CallRepository = Depends(get_call_repository),
    db: Session = Depends(get_db),
):
    """
    Recupere un appel par id.
    Avec with_osint=true, joint phone_number_profiles comme pour la liste.
    """
    call = call_repo.get_by_id(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Appel non trouvé")

    if not with_osint:
        return CallResponse.model_validate(call)

    data = CallResponse.model_validate(call).model_dump()
    if call.phone_number:
        profile = (
            db.query(PhoneNumberProfile)
            .filter(PhoneNumberProfile.phone_number == call.phone_number)
            .order_by(desc(PhoneNumberProfile.last_checked_at))
            .first()
        )
        if profile:
            data["osint"] = _profile_to_osint_response(profile, call.phone_number)
        else:
            data["osint"] = None
    else:
        data["osint"] = None
    return CallResponse(**data)


@router.delete("/calls/{call_id}")
async def delete_call(
    call_id: int,
    call_repo: CallRepository = Depends(get_call_repository),
    config: Config = Depends(get_config),
):
    """Supprime un appel et le fichier audio recordings/ s'il existe."""
    call = call_repo.get_by_id(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Appel non trouvé")
    _try_unlink_recording(config, call.audio_file)
    if not call_repo.delete(call_id):
        raise HTTPException(status_code=404, detail="Appel non trouvé")

    return {"message": "Appel supprimé"}


@router.post("/calls/outgoing/start", response_model=OutgoingCallActionResponse)
async def start_outgoing_call(
    payload: OutgoingCallStartRequest,
    request: Request,
    config: Config = Depends(get_config),
):
    """Demarre un appel sortant depuis la page Appels."""
    if _should_proxy_outgoing_to_daemon(config, request):
        return await _proxy_outgoing_to_telephony(
            request,
            config,
            "/api/v1/calls/outgoing/start",
            {"phone_number": payload.phone_number},
        )
    call_manager = getattr(request.app.state, "call_manager", None)
    if call_manager is None:
        raise HTTPException(status_code=503, detail="Call manager indisponible")
    if not call_manager.modem.is_initialized:
        raise HTTPException(status_code=503, detail="Modem non initialise")

    phone = payload.phone_number.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Numero invalide")

    call = await call_manager.call_service.create_outgoing_call(phone)
    session = OutgoingCallSession(call_id=call.id, phone_number=phone)
    outgoing_sessions[call.id] = session
    asyncio.create_task(_publish_log(call.id, phone, "Session sortante creee (tache modem)"))
    asyncio.create_task(_run_outgoing_call_session(request.app, session))
    return OutgoingCallActionResponse(ok=True, call_id=call.id, message="Appel sortant demarre")


@router.post("/calls/outgoing/{call_id}/dtmf", response_model=OutgoingCallActionResponse)
async def outgoing_send_dtmf(
    call_id: int,
    payload: DtmfRequest,
    request: Request,
    config: Config = Depends(get_config),
):
    """Envoie une touche DTMF au modem pendant l'appel."""
    if _should_proxy_outgoing_to_daemon(config, request):
        return await _proxy_outgoing_to_telephony(
            request,
            config,
            f"/api/v1/calls/outgoing/{call_id}/dtmf",
            {"digit": payload.digit},
        )
    call_manager = getattr(request.app.state, "call_manager", None)
    if call_manager is None:
        raise HTTPException(status_code=503, detail="Call manager indisponible")
    session = outgoing_sessions.get(call_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session d'appel sortant introuvable")

    digit = payload.digit.strip()
    ok = await call_manager.modem.send_dtmf(digit)
    if not ok:
        await _publish_log(call_id, session.phone_number, f"DTMF {digit} refuse par le modem", "error")
        raise HTTPException(status_code=400, detail="Echec envoi DTMF")
    await _publish_log(call_id, session.phone_number, f"DTMF envoye: {digit}")
    return OutgoingCallActionResponse(ok=True, call_id=call_id, message=f"DTMF {digit} envoye")


@router.post("/calls/outgoing/{call_id}/hangup", response_model=OutgoingCallActionResponse)
async def outgoing_hangup(
    call_id: int,
    request: Request,
    config: Config = Depends(get_config),
):
    """Raccroche un appel sortant en cours."""
    if _should_proxy_outgoing_to_daemon(config, request):
        return await _proxy_outgoing_to_telephony(
            request,
            config,
            f"/api/v1/calls/outgoing/{call_id}/hangup",
            {},
        )
    session = outgoing_sessions.get(call_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session d'appel sortant introuvable")
    asyncio.create_task(_publish_log(call_id, session.phone_number, "Raccrochage demande depuis l'UI"))
    session.stop_event.set()
    return OutgoingCallActionResponse(ok=True, call_id=call_id, message="Raccrochage demande")


@router.patch("/calls/{call_id}/tag")
async def patch_call_tag(
    call_id: int,
    body: CallTagUpdate,
    call_repo: CallRepository = Depends(get_call_repository),
    block_service: BlockService = Depends(get_block_service),
):
    """Met a jour le tag UI d'un appel (extra_data.ui_tag) et synchronise liste blanche / noire si besoin."""
    call = call_repo.get_by_id(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Appel non trouve")

    meta = dict(call.extra_data or {})
    if body.tag == "none":
        meta.pop("ui_tag", None)
    else:
        meta["ui_tag"] = body.tag

    pn = call.phone_number
    if pn:
        if body.tag == "permitted":
            await block_service.whitelist_caller(pn)
        elif body.tag == "blocked":
            await block_service.block_caller(pn, reason="ui_tag_blocked")

    call_repo.update(call_id, extra_data=meta)
    return {"ok": True, "call_id": call_id, "tag": body.tag}


@router.post("/calls/{call_id}/osint/queue")
async def queue_call_osint(call_id: int, db: Session = Depends(get_db)):
    """Remet en file d'attente une tache Celery pour enrichir le numero de cet appel."""
    call_repo = CallRepository(db)
    call = call_repo.get_by_id(call_id)
    if not call or not call.phone_number:
        raise HTTPException(status_code=404, detail="Appel ou numero introuvable")

    svc = PhoneOsintService(db, Config())
    svc.force_queue_refresh(call.phone_number)
    return {"ok": True, "call_id": call_id, "phone_number": call.phone_number}

