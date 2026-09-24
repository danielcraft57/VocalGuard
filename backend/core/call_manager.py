"""
Gestionnaire d'appels - Orchestre le traitement des appels entrants
Version améliorée avec services et événements
"""

import asyncio
import os
import tempfile
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from loguru import logger
from sqlalchemy.orm import Session

from backend.core.config import Config
from backend.core.modem_handler import ModemHandler, _vrx_buffer_has_hangup_marker
from backend.core.events import Event, EventType, event_bus
from backend.core.phone_cid import classify_cid_outcome, normalize_cid_value
from backend.core.incoming_line_schedule import apply_schedule_to_auto_answer
from backend.core.incoming_call_policy import IncomingCallPolicy
from backend.core.incoming_call_audio import (
    blocked_message_text,
    ensure_default_voice_assets,
    greeting_intro_path,
    greeting_text,
    pick_wav_or_none,
    refresh_modem_voice_assets,
    resolve_intro_voice_bed_gain_db,
    resolve_resource_path,
    beep_wav_path,
)
from backend.core.incoming_call_settings import (
    load_incoming_call_settings,
    apply_incoming_call_settings,
    resolve_profile_decision,
)
from backend.voice.recognition import VoiceRecognition
from backend.voice.synthesis import VoiceSynthesis
from backend.voice.ivr_patterns import IvrPatternsEngine
from backend.voice.audio_utils import (
    combine_intro_voice_crossfade,
    combine_music_track_voice_overlay,
    combine_modem_wav_files,
    default_bed_variant_for_jingle,
    export_wav_8k_8bit,
    load_wav_as_16k16bit_pcm,
    pcm_chunk_peak,
    pcm_modem_to_s16le_16k,
    trim_leading_trailing_silence,
    tts_source_to_modem_wav,
    wav_matches_modem_profile,
    write_beep_wav_8k,
    write_talk_cue_wav_8k,
)
from backend.voice.ivr_cache import IvrAudioCache
from backend.voice.modem_profile import resolve_profile_from_config

DEFAULT_VOICEMAIL_GREETING = (
    "Bonjour, vous êtes bien chez DanielCraft, de Loïc Daniel, "
    "merci de laisser un message."
)
VOICEMAIL_GOODBYE = "Merci, votre message a bien été enregistré. Au revoir."
from backend.services.call_service import CallService
from backend.services.block_service import BlockService
from backend.services.appointment_service import AppointmentService
from backend.services.conversation_service import ConversationService
from backend.database.database import get_db
from backend.database.models import Call


class _IncomingLineRecorder:
    """Capture audio ligne (VRX) pendant un appel entrant ; pause pendant VTX."""

    def __init__(self, call_manager: "CallManager") -> None:
        self._cm = call_manager
        self.chunks: list[bytes] = []
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._active = False
        # True seulement apres start() reussi : evite resume() apres bip en mode simple
        # (qui rouverait VRX et bloquerait l'enregistrement / le raccrochage).
        self._session = False
        # Octets PCM de l'accueil injecte (seed) — pour decaler le karaoke SRT.
        self.seed_pcm_bytes: int = 0

    async def start(self, already_in_voice_mode: bool = True) -> None:
        """
        Ouvre le flux VRX et demarre la capture PCM ligne.

        Idempotent : si deja actif, no-op ; si session en pause, resume.

        @param already_in_voice_mode True si FCLASS=8 / VLS=1 deja faits.
        """
        if not self._cm._use_modem_voice_serial():
            return
        if self._session and self._active:
            return
        if self._session and not self._active:
            await self.resume(already_in_voice_mode=already_in_voice_mode)
            return
        ok = await self._cm.modem.start_outgoing_vrx_stream(already_in_voice_mode=already_in_voice_mode)
        if not ok:
            logger.warning("Enregistrement entrant: impossible d'ouvrir VRX")
            return
        self._session = True
        self._active = True
        self._stop.clear()
        self._task = asyncio.create_task(self._read_loop(), name="incoming_vrx_recorder")

    async def _read_loop(self) -> None:
        max_chunks = 9000  # ~ ~30 min a ~2 ko/chunk ; coupe les pics memoire
        while not self._stop.is_set():
            chunk = await self._cm.modem.read_outgoing_vrx_chunk(2048)
            if self._cm.modem.caller_line_finished():
                logger.info("Enregistrement entrant: raccrochage distant (VRX)")
                break
            if chunk:
                self.chunks.append(chunk)
                if len(self.chunks) > max_chunks:
                    # Garde la fin (message recent) pour ne pas exploser la RAM.
                    self.chunks = self.chunks[-max_chunks // 2 :]
            else:
                await asyncio.sleep(0.02)

    async def pause(self) -> None:
        if not self._session or not self._active:
            return
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
        try:
            await self._cm.modem.end_outgoing_vrx_stream()
        except Exception:
            pass
        self._active = False
        self._stop.clear()

    async def detach_reader(self) -> None:
        """
        Arrete la boucle lecture sans fermer le flux VRX.

        Utile en debut de conversation : l'enregistreur tourne deja depuis le
        seize ; on passe la main a l'ecoute STT sans creer un trou audio.

        @returns None
        """
        if not self._session or not self._active:
            return
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
        self._active = False
        self._stop.clear()

    async def resume(self, already_in_voice_mode: bool = True) -> None:
        """Reprend VRX seulement si start() a ouvert une session (mode IVR)."""
        if not self._session or not self._cm._use_modem_voice_serial():
            return
        if self._active:
            return
        ok = await self._cm.modem.start_outgoing_vrx_stream(already_in_voice_mode=already_in_voice_mode)
        if not ok:
            return
        self._active = True
        self._stop.clear()
        self._task = asyncio.create_task(self._read_loop(), name="incoming_vrx_recorder")

    def append_pcm(self, data: bytes) -> None:
        """
        Ajoute un chunk PCM brut modem a l'enregistrement.

        @param data Octets PCM (format profil modem).
        """
        if data:
            self.chunks.append(data)

    def mark_seed_pcm(self, data: bytes) -> None:
        """
        Enregistre la taille du seed accueil (deja append via append_pcm).

        @param data PCM de l'accueil injecte.
        """
        if data:
            self.seed_pcm_bytes += len(data)

    def seed_duration_sec(self) -> float:
        """
        Duree de l'accueil pre-colle en tete du WAV.

        @returns Secondes (0 si pas de seed), plafonne a 8 s (garde-fou).
        """
        if self.seed_pcm_bytes <= 0:
            return 0.0
        profile = getattr(self._cm.modem, "voice_profile", None)
        bps = int(getattr(profile, "bytes_per_sec", 0) or 0)
        if bps <= 0:
            rate = int(getattr(profile, "sample_rate", 8000) or 8000)
            width = int(getattr(profile, "sample_width", 1) or 1)
            bps = max(1, rate * width)
        return min(8.0, float(self.seed_pcm_bytes) / float(bps))

    async def save(self, call_id: int) -> None:
        await self.pause()
        self._active = False
        self._session = False
        if not self.chunks:
            return
        base = Path(self._cm.config.base_path) if self._cm.config.base_path else Path.cwd()
        recordings_dir = base / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        wav_rel = f"recordings/call_in_{call_id}_{ts}.wav"
        wav_path = base / wav_rel
        profile = self._cm.modem.voice_profile
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(profile.sample_width)
            wf.setframerate(profile.sample_rate)
            wf.writeframes(b"".join(self.chunks))
        await self._cm.call_service.set_audio_file(call_id, wav_rel)
        logger.info("Appel entrant enregistré: {}", wav_rel)


class CallManager:
    """Gère les appels entrants et leur traitement"""
    
    def __init__(self, config: Config, db: Session):
        """
        Initialise le gestionnaire d'appels
        
        Args:
            config: Configuration de l'application
            db: Session de base de données
        """
        self.config = config
        self.db = db
        self.modem = ModemHandler(config.modem_port, config.modem_baudrate)
        from backend.core.telephony_transport import (
            TelephonyBackend,
            create_telephony_transport,
            parse_telephony_backend,
        )

        self.telephony_backend = parse_telephony_backend(
            getattr(config, "telephony_backend", "modem")
        )
        if self.telephony_backend == TelephonyBackend.VOIP:
            self.transport = create_telephony_transport(TelephonyBackend.VOIP)
        else:
            self.transport = create_telephony_transport(
                self.telephony_backend, modem=self.modem
            )
        self.voice_recognition = VoiceRecognition(config)
        self.voice_synthesis = VoiceSynthesis(config)
        self.ivr_engine = IvrPatternsEngine(config)
        
        # Services
        self.call_service = CallService(db)
        self.block_service = BlockService(config, db)
        self.appointment_service = AppointmentService(db)

        # Service de conversation base sur patterns metier
        self.conversation_service = ConversationService()
        
        self.is_running = False
        self.current_call_id: Optional[int] = None
        self._incoming_recorder: Optional[_IncomingLineRecorder] = None
        self._skip_incoming_recording_save: bool = False
        self._incoming_handling = False
        self._line_already_answered = False
        self._pending_cid: Optional[str] = None
        self._pending_cname: Optional[str] = None
        self._cid_event: Optional[asyncio.Event] = None
        self._cname_event: Optional[asyncio.Event] = None
        self._voice_available = True  # False si STT ou TTS non disponibles (app demarre quand meme)
        self._recognition_available = False
        self._call_deadline: Optional[float] = None
        self._last_ring_seen: float = 0.0
        self._phone_mode_ring_event: Optional[asyncio.Event] = None
        self._call_rings_heard: int = 0
        self._active_call_monotonic: Optional[float] = None
        self._pending_call_duration_sec: Optional[int] = None
        self._call_db_finalized: bool = False
        self._modem_recover_lock = asyncio.Lock()

        # Mode audio modem: voix série (Conexant) ou ALSA. USE_MODEM_VOICE_MODE=0 force ALSA (evite ton aigu).
        _voice_env = os.environ.get("USE_MODEM_VOICE_MODE", "").strip().lower()
        self._force_alsa = _voice_env in ("0", "false", "no")
        self._use_voice_serial = not self._force_alsa and _voice_env in ("1", "true", "yes")
        self._alsa_play = os.environ.get("ALSA_MODEM_DEVICE") or os.environ.get("ALSA_DEVICE", "default")
        self._alsa_record = os.environ.get("ALSA_MODEM_RECORD_DEVICE") or self._alsa_play
        self._ivr_wav_dir: Optional[Path] = None
        self._ivr_cache = IvrAudioCache(config, self.voice_synthesis)
        self.incoming_policy = IncomingCallPolicy(config)
        
        # Enregistrer les handlers d'événements
        self._setup_event_handlers()

    def get_voip_transport(self):
        """
        Retourne le VoipTransport si backend voip ou dual.

        @returns VoipTransport ou None.
        """
        from backend.core.telephony_transport import DualTransport, VoipTransport

        t = getattr(self, "transport", None)
        if isinstance(t, VoipTransport):
            return t
        if isinstance(t, DualTransport):
            return t.voip
        return None

    def _log_call(self, phase: str, **fields: Any) -> None:
        """
        Journalise une etape du flux appel entrant (grep [APPEL]).

        @param phase Identifiant court (ex. ring_debut, release).
        @param fields Paires cle=valeur supplementaires.
        """
        modem = getattr(self, "modem", None)
        voice = modem.voice_session_diag() if modem and hasattr(modem, "voice_session_diag") else {}
        parts = [f"phase={phase}"]
        if self.current_call_id is not None:
            parts.append(f"call_id={self.current_call_id}")
        parts.append(f"handling={int(self._incoming_handling)}")
        for key, value in fields.items():
            parts.append(f"{key}={value}")
        if voice:
            parts.append(
                "modem vtx={vtx} seize={seize}/{seize_ok} line={line_ready} abort={abort}".format(
                    **voice
                )
            )
        logger.info("[APPEL] {}", " ".join(parts))

    async def request_ui_hangup(self, call_id: int) -> bool:
        """
        Raccrochage demande depuis l'UI pendant un appel entrant actif.

        @param call_id Identifiant de l'appel en cours.
        @returns True si la demande est acceptee (idempotent si autre appel).
        """
        if self.current_call_id is not None and int(call_id) != int(self.current_call_id):
            self._log_call(
                "ui_hangup_ignore",
                demande=call_id,
                actif=self.current_call_id,
            )
            return True
        self._log_call("ui_hangup", demande=call_id)
        await self.release_active_call(reason="ui_hangup", complete=True, call_id=call_id)
        return True

    def _call_still_active(self, call_id: Optional[int] = None) -> bool:
        """
        True si l'appel est encore considere actif cote logiciel.

        @param call_id ID attendu (optionnel).
        @returns False apres release / ui_hangup.
        """
        if self.current_call_id is None:
            return False
        if call_id is not None and int(self.current_call_id) != int(call_id):
            return False
        if getattr(self.modem, "_voice_abort", False):
            return False
        return True

    async def _finalize_call_db(self, call_id: int, *, complete: bool = True) -> None:
        """
        Cloture l'appel en base et notifie le frontend sans attendre le modem.

        @param call_id Identifiant appel.
        @param complete True = completed, False = missed.
        @returns None
        """
        if self._call_db_finalized:
            return
        duration_sec = self._pending_call_duration_sec
        if duration_sec is None and self._active_call_monotonic is not None:
            duration_sec = max(1, int(time.monotonic() - self._active_call_monotonic))
        if self.current_call_id == call_id:
            self.current_call_id = None
        self._incoming_handling = False
        try:
            if complete:
                await self.call_service.complete_call(call_id, duration=duration_sec)
            else:
                await self.call_service.miss_call(call_id)
        except Exception as exc:
            logger.warning("_finalize_call_db call {}: {}", call_id, exc)
        else:
            self._call_db_finalized = True
            self._log_call(
                "call_finalise_precoce",
                db_id=call_id,
                duree_s=duration_sec or 0,
                complete=int(complete),
            )
        self._active_call_monotonic = None
        self._pending_call_duration_sec = None

    async def _modem_release_background(self, reason: str) -> None:
        """
        Raccroche le modem en arriere-plan (ATH obligatoire apres VLS=1).

        @param reason Motif log.
        @returns None
        """
        async with self._modem_recover_lock:
            m = self.modem
            m._voice_abort = True
            m._playback_interrupted = True
            hangup_ok = False
            try:
                self._log_call("release_modem_rapide", raison=reason)
                # ATH d'abord : FCLASS=0 seul laisse la ligne OQP apres seize voix.
                hangup_ok = bool(
                    await m.run_modem_sync(m._force_hangup_sync, timeout=4.0)
                )
            except asyncio.TimeoutError:
                logger.warning("[APPEL] force hangup timeout ({})", reason)
            except Exception as exc:
                logger.warning("[APPEL] force hangup echoue ({}): {}", reason, exc)
            if not hangup_ok:
                try:
                    hangup_ok = bool(
                        await m.run_modem_sync(
                            m._fast_cleanup_after_remote_hangup_sync,
                            timeout=3.0,
                        )
                    )
                except Exception as exc:
                    logger.warning("[APPEL] fast_cleanup echoue ({}): {}", reason, exc)
            if not hangup_ok:
                try:
                    await m.run_modem_sync(m._force_serial_reset_sync, timeout=1.0)
                except Exception:
                    pass
                try:
                    ok = await m.reconnect(attempts=6)
                    if ok:
                        # Reconnect n'envoie plus ATH : on force encore on-hook.
                        try:
                            await m.run_modem_sync(
                                m._fast_cleanup_after_remote_hangup_sync,
                                timeout=3.0,
                            )
                        except Exception:
                            pass
                        logger.info("[MODEM] reconnect OK apres release ({})", reason)
                    else:
                        logger.warning("[MODEM] reconnect echoue apres release ({})", reason)
                except Exception as exc:
                    logger.warning("[MODEM] reconnect exception release ({}): {}", reason, exc)
            if hasattr(m, "log_voice_session"):
                m.log_voice_session(f"release_modem_fin ({reason}) hangup_ok={int(hangup_ok)}")

    async def release_active_call(
        self,
        *,
        reason: str = "release",
        complete: bool = True,
        call_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Libere l'etat logiciel d'appel et lance le raccrochage modem en arriere-plan.

        L'etat UI (in_call) et l'evenement call.completed sont remis a zero tout de suite.

        @param reason Motif log.
        @param complete True = complete_call, False = miss_call.
        @param call_id ID explicite (sinon current_call_id).
        @returns Resume {released_call_id, hangup_ok, in_call}.
        """
        target_id = call_id if call_id is not None else self.current_call_id
        self._log_call(
            "release_debut",
            reason=reason,
            target_id=target_id,
            complete=int(complete),
        )
        if hasattr(self.modem, "log_voice_session"):
            self.modem.log_voice_session(f"release_debut ({reason})")

        self.modem._voice_abort = True
        self.modem._playback_interrupted = True
        self.current_call_id = None
        self._incoming_handling = False
        self._incoming_recorder = None

        if target_id and not self._call_db_finalized:
            duration_sec = self._pending_call_duration_sec
            if duration_sec is None and self._active_call_monotonic is not None:
                duration_sec = max(1, int(time.monotonic() - self._active_call_monotonic))
            try:
                if complete:
                    await self.call_service.complete_call(target_id, duration=duration_sec)
                else:
                    await self.call_service.miss_call(target_id)
            except Exception as exc:
                logger.warning("release_active_call db call {}: {}", target_id, exc)
            else:
                self._call_db_finalized = True

        self._active_call_monotonic = None
        self._pending_call_duration_sec = None

        try:
            self.modem.clear_incoming_seize()
        except Exception as exc:
            logger.warning("clear_incoming_seize: {}", exc)

        asyncio.create_task(
            self._modem_release_background(reason),
            name=f"modem_release_{reason}",
        )

        result = {
            "released_call_id": target_id,
            "hangup_ok": 1,
            "in_call": 0,
        }
        self._log_call("release_fin", reason=reason, async_modem=1, **result)
        if hasattr(self.modem, "log_voice_session"):
            self.modem.log_voice_session(f"release_fin ({reason}) async=1")
        return result

    async def _recover_modem_after_failed_hangup(self) -> None:
        """
        Reconnexion serie apres ATH bloque ou timeout (evite modem KO jusqu'au restart).

        @returns None
        """
        async with self._modem_recover_lock:
            try:
                await self.modem.run_modem_sync(self.modem._force_serial_reset_sync, timeout=1.0)
                ok = await self.modem.reconnect(attempts=8)
                if ok:
                    logger.info("[MODEM] reconnect OK apres echec hangup")
                else:
                    logger.warning("[MODEM] reconnect echoue apres echec hangup")
            except Exception as exc:
                logger.warning("[MODEM] recover apres hangup: {}", exc)
    
    def _ensure_ivr_wav_dir(self) -> Path:
        if self._ivr_wav_dir is None:
            base = Path(self.config.base_path) if self.config.base_path else Path(".")
            self._ivr_wav_dir = base / "ivr_wav"
            self._ivr_wav_dir.mkdir(parents=True, exist_ok=True)
        return self._ivr_wav_dir

    def _use_modem_voice_serial(self) -> bool:
        if self._force_alsa:
            return False
        return self._use_voice_serial or (self.modem.is_initialized and self.modem.supports_voice_serial)
    
    def _setup_event_handlers(self):
        """Configure les handlers d'événements"""
        event_bus.subscribe(EventType.CALL_INCOMING, self._on_call_incoming)
        event_bus.subscribe(EventType.CALL_BLOCKED, self._on_call_blocked)
        event_bus.subscribe(EventType.CALL_COMPLETED, self._on_call_completed)
    
    async def _on_call_incoming(self, event: Event):
        """Handler pour les appels entrants"""
        logger.debug(f"Événement reçu: {event.event_type}")
    
    async def _on_call_blocked(self, event: Event):
        """Handler pour les appels bloqués"""
        logger.debug(f"Appel bloqué: {event.data.get('call_id')}")
    
    async def _on_call_completed(self, event: Event):
        """Handler pour les appels terminés"""
        logger.debug(f"Appel terminé: {event.data.get('call_id')}")
    
    async def initialize(self):
        """Initialise tous les composants"""
        logger.info("Initialisation du gestionnaire d'appels...")
        
        # Modem : sur l API principale avec USE_TELEPHONY_DAEMON=1 le modem est sur le daemon (ex. node14).
        # Ne pas ouvrir MODEM_PORT ici (evite /dev/ttyACM0 sur Windows et traces inutiles).
        modem_initialized = False
        from backend.core.telephony_transport import TelephonyBackend, DualTransport, VoipTransport

        if self.telephony_backend == TelephonyBackend.VOIP:
            await self.transport.start()
            logger.info("Transport VoIP stub initialise (pas de modem)")
        elif self.config.use_telephony_daemon:
            logger.info(
                "USE_TELEPHONY_DAEMON=1 : modem gere par le service telephony — pas de port serie sur ce processus."
            )
        else:
            # Appliquer gains / pays / VDR depuis la config avant init modem.
            self._apply_modem_runtime_options()
            modem_initialized = await self.modem.initialize()
            if not modem_initialized:
                logger.warning("Modem non disponible - l'API fonctionnera sans gestion d'appels")
            else:
                self.modem.on_incoming_call = self.handle_incoming_call
                logger.info("Modem initialisé")
            if isinstance(self.transport, DualTransport):
                await self.transport.start()
                logger.info("Transport dual : modem + VoIP stub")
            elif modem_initialized:
                await self.transport.start()

        # Initialiser la reconnaissance vocale (optionnel : si absent, pas de transcription IVR)
        try:
            await self.voice_recognition.initialize()
            self._recognition_available = self.voice_recognition.is_available()
        except Exception as e:
            logger.warning(
                "Reconnaissance vocale indisponible (VOSK/Whisper). "
                "Appels pris en charge mais sans transcription. Erreur: %s",
                e,
            )
            self._recognition_available = False
            self._voice_available = False

        # Initialiser la synthèse vocale (optionnel)
        try:
            await self.voice_synthesis.initialize()
        except Exception as e:
            logger.warning(
                "Synthèse vocale indisponible. Appels pris en charge sans TTS. Erreur: %s",
                e,
            )
            self._voice_available = False

        if self._voice_available:
            ensure_default_voice_assets(self.config)
            logger.info(
                "TTS accueil: voix={} pitch={} rate={}",
                getattr(self.config, "edge_tts_voice", "?"),
                getattr(self.config, "edge_tts_pitch", "?"),
                getattr(self.config, "edge_tts_rate", "?"),
            )
            await self._warmup_ivr_cache()

        logger.info(
            "Gestionnaire d'appels initialisé (STT: %s, TTS: %s)",
            "activée" if self._recognition_available else "désactivée",
            "activée" if self._voice_available else "désactivée",
        )

    def _greeting_text(self) -> str:
        if hasattr(self, "incoming_policy"):
            return greeting_text(self.config, self.incoming_policy.settings)
        greeting = (self.config.voicemail_greeting or "").strip()
        return greeting or DEFAULT_VOICEMAIL_GREETING

    def _audio_settings(self):
        """Bloc audio incoming_call (ou defauts)."""
        if hasattr(self, "incoming_policy"):
            return self.incoming_policy.settings.audio
        return load_incoming_call_settings(self.config).audio

    def _voicemail_settings(self):
        """Bloc messagerie / DTMF incoming_call (ou defauts)."""
        if hasattr(self, "incoming_policy"):
            return self.incoming_policy.settings.voicemail
        return load_incoming_call_settings(self.config).voicemail

    def _is_conversation_mode(self) -> bool:
        """
        True si le repondeur est en mode dialogue intents KB.

        @returns Mode conversation actif.
        """
        vm = self._voicemail_settings()
        mode = (
            getattr(vm, "mode", None)
            or getattr(self.config, "voicemail_mode", "simple")
            or "simple"
        )
        return str(mode).strip().lower() == "conversation"

    def _conversation_salutation_text(self) -> str:
        """
        Texte d'ouverture style tchat KB (intent salutation).

        @returns Premiere reponse catalogue, ou defaut chat-like.
        """
        default = (
            "Bonjour, assistante de monsieur Daniel. "
            "Comment puis-je vous aider ?"
        )
        try:
            from backend.database import database as db_module
            from backend.services import intent_repository as intent_repo

            if db_module.SessionLocal is None:
                return default
            db = db_module.SessionLocal()
            try:
                intent = intent_repo.get_intent_by_tag(db, "salutation")
                if intent is not None and intent.responses:
                    texts = [
                        (r.text or "").strip()
                        for r in sorted(intent.responses, key=lambda x: x.position)
                    ]
                    texts = [t for t in texts if t]
                    if texts:
                        preferred = (
                            "Bonjour, assistante de monsieur Daniel. "
                            "Comment puis-je vous aider ?"
                        )
                        for t in texts:
                            if "assistante de monsieur daniel" in t.lower():
                                return t
                        if preferred in texts:
                            return preferred
                        return texts[0]
            finally:
                db.close()
        except Exception:
            logger.debug("Texte salutation KB indisponible — defaut")
        return default

    def _conversation_greeting_wav(self) -> Optional[Path]:
        """
        WAV precharge de l'intent salutation (meme voix que le catalogue KB).

        Preferre le cache IVR frais (texte KB courant), sinon fichier historique.

        @returns Chemin ivr_wav/kb_salutation.wav si present.
        """
        text = self._conversation_salutation_text()
        fresh = self._ivr_cache.get_if_fresh(text, "kb_salutation")
        if fresh is not None and fresh.is_file() and fresh.stat().st_size >= 2000:
            return fresh
        base = Path(self.config.base_path) if self.config.base_path else Path.cwd()
        path = base / "ivr_wav" / "kb_salutation.wav"
        if path.is_file() and path.stat().st_size >= 2000:
            return path
        return None

    async def _play_conversation_opening(
        self,
        *,
        already_in_voice_mode: bool = True,
        recorder: Optional["_IncomingLineRecorder"] = None,
    ) -> bool:
        """
        Joue l'ouverture dialogue (salutation KB), sans message 'laissez un message'.

        @param already_in_voice_mode Ligne deja en mode voix.
        @param recorder Enregistreur parallele.
        @returns True si lecture OK.
        """
        wav = self._conversation_greeting_wav()
        if wav is not None:
            self._log_call("accueil_conversation", fichier=wav.name)
            return await self._play_wav_file_on_line(
                wav,
                already_in_voice_mode=already_in_voice_mode,
                recorder=recorder,
            )
        text = self._conversation_salutation_text()
        self._log_call("accueil_conversation", source="tts")
        return await self._play_on_line(
            text,
            already_in_voice_mode=already_in_voice_mode,
            recorder=recorder,
        )

    def _resolve_conversation_wait_wav(self) -> Optional[Path]:
        """
        Jingle / bed d'attente pendant STT (assets projet deja presents).

        Priorite : bed modem lab (bouclable) > sting mini > generation cache.

        @returns Chemin WAV 8 kHz modem, ou None.
        """
        base = Path(self.config.base_path) if self.config.base_path else Path.cwd()
        candidates = [
            base / "ivr_wav" / "conversation_wait.wav",
            base / "resources" / "voice" / "lab" / "beds" / "bed_calm_wave_MODEM.wav",
            base / "resources" / "voice" / "lab" / "jingles" / "sting_mini_MODEM.wav",
            base / "resources" / "voice" / "intros" / "sting_mini.wav",
            base / "resources" / "voice" / "intros" / "sting_marimba.wav",
        ]
        for path in candidates:
            try:
                if path.is_file() and path.stat().st_size >= 1500:
                    return path
            except OSError:
                continue
        # Genere un sting court dans le cache IVR si rien n'est dispo.
        out = base / "ivr_wav" / "conversation_wait.wav"
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            from backend.voice.audio_utils import write_stinger_intro_wav

            write_stinger_intro_wav(out, variant="sting_mini", duration_ms=1800)
            if out.is_file() and out.stat().st_size >= 1500:
                return out
        except Exception:
            logger.debug("Generation jingle attente conversation ignoree")
        return None

    async def _transcribe_with_wait_jingle(
        self,
        turn_pcm: bytes,
        *,
        client,
        recorder: Optional["_IncomingLineRecorder"],
        turn_idx: int,
    ) -> str:
        """
        STT final avec jingle d'attente en parallele (remplit le silence ligne).

        Le STT n'utilise pas le port serie ; le play oui. On coupe le jingle
        des que la transcription est prete. Audio trimme + plafonne pour
        limiter la latence Whisper.

        @param turn_pcm PCM 16 kHz 16-bit du tour.
        @param client Client node15 (peut etre None → fallback local).
        @param recorder Enregistreur ligne.
        @param turn_idx Index de tour (logs).
        @returns Texte transcrit (peut etre vide).
        """
        pcm_for_stt = self._prepare_conversation_stt_pcm(turn_pcm)
        wait_wav = self._resolve_conversation_wait_wav()
        done = asyncio.Event()
        result_box: dict[str, object] = {"text": "", "engine": "?"}

        async def _run_stt() -> None:
            try:
                if client is not None:
                    # live = sans timestamps, plus rapide sur whisper-server
                    result = await client.transcribe(pcm_for_stt, mode="final")
                    result_box["text"] = (result.get("text") or "").strip()
                    result_box["engine"] = result.get("engine") or "whisper"
                elif self._recognition_available:
                    text, _ = await self.voice_recognition.transcribe_with_cues(
                        pcm_for_stt, sample_rate=16000
                    )
                    result_box["text"] = (text or "").strip()
                    result_box["engine"] = "local"
            except Exception:
                logger.exception("STT final tour {}", turn_idx)
                result_box["text"] = ""
            finally:
                done.set()
                # Coupe le VTX jingle si encore en cours.
                try:
                    self.modem._voice_abort = True
                except Exception:
                    pass

        stt_task = asyncio.create_task(_run_stt(), name=f"stt_wait_{turn_idx}")
        try:
            if wait_wav is not None:
                self._log_call("attente_jingle", fichier=wait_wav.name, turn=turn_idx)
                # Boucle courte tant que le STT n'a pas fini.
                while not done.is_set():
                    if self.modem.caller_line_finished():
                        break
                    try:
                        self.modem._voice_abort = False
                    except Exception:
                        pass
                    await self._play_wav_file_on_line(
                        wait_wav,
                        already_in_voice_mode=self._use_modem_voice_serial(),
                        recorder=recorder,
                    )
                    if done.is_set():
                        break
                    await asyncio.sleep(0.05)
            else:
                await done.wait()
        finally:
            try:
                self.modem._voice_abort = False
            except Exception:
                pass
            if not stt_task.done():
                await stt_task
            else:
                # Drain exceptions deja loggees.
                try:
                    stt_task.result()
                except Exception:
                    pass

        final_text = str(result_box.get("text") or "").strip()
        logger.info(
            "STT node15 tour {} : {} car. ({}) [wait_jingle={} pcm={}→{}]",
            turn_idx,
            len(final_text),
            result_box.get("engine") or "?",
            wait_wav.name if wait_wav else "off",
            len(turn_pcm),
            len(pcm_for_stt),
        )
        return final_text

    def _prepare_conversation_stt_pcm(
        self, turn_pcm: bytes, *, max_sec: float = 6.0
    ) -> bytes:
        """
        Reduit le PCM avant Whisper : trim silence + plafond duree.

        @param turn_pcm PCM 16 kHz 16-bit.
        @param max_sec Plafond (live ~3.2 s, final ~6 s).
        @returns PCM optimise (jamais vide si entree non vide).
        """
        if not turn_pcm:
            return turn_pcm
        pcm = turn_pcm
        # Trim silence tete/queue (threshold bas pour modem bruyant).
        try:
            import array

            samples = array.array("h")
            samples.frombytes(pcm)
            if len(samples) > 800:  # >50 ms
                thr = 400
                n = len(samples)
                start = 0
                while start < n and abs(samples[start]) < thr:
                    start += 1
                end = n - 1
                while end > start and abs(samples[end]) < thr:
                    end -= 1
                # Garde 80 ms de marge
                pad = 1280
                start = max(0, start - pad)
                end = min(n - 1, end + pad)
                if end > start + 1600:
                    pcm = samples[start : end + 1].tobytes()
        except Exception:
            logger.debug("Trim STT conversation ignore")
        # Plafond : Whisper base, latence ~lineaire a la duree.
        max_bytes = int(16000 * 2 * max(1.0, float(max_sec)))
        if len(pcm) > max_bytes:
            pcm = pcm[-max_bytes:]
        return pcm or turn_pcm

    def _needs_dtmf_gate(self, decision=None) -> bool:
        """
        True si le filtre DTMF anti-robots doit s'executer avant enregistrement.

        @param decision Decision policy courante (optionnel).
        @returns Active si require_dtmf ou action dtmf_gate.
        """
        vm = self._voicemail_settings()
        if vm.require_dtmf:
            return True
        if decision and "dtmf_gate" in (decision.actions or []):
            return True
        return False

    async def _run_dtmf_gate(self) -> bool:
        """
        Joue le prompt DTMF puis attend la touche configuree.

        @returns True si la bonne touche a ete recue.
        """
        vm = self._voicemail_settings()
        prompt = (vm.dtmf_prompt_text or "Tapez 1 pour laisser un message.").strip()
        await self._play_configured_message(
            source=vm.dtmf_prompt_source,
            wav_path=None,
            tts_text=prompt,
            fallback_text=prompt,
            already_in_voice_mode=True,
            recorder=self._incoming_recorder,
        )
        digit = (vm.dtmf_digit or "1").strip()[:1]
        timeout = float(vm.dtmf_timeout_sec or 8.0)
        return await self.modem.wait_for_dtmf_digit(digit, timeout)

    def _ivr_basename_for_text(self, text: str) -> Optional[str]:
        normalized = text.strip()
        if normalized == self._greeting_text().strip():
            return "voicemail_greeting"
        if normalized == VOICEMAIL_GOODBYE:
            return "voicemail_goodbye"
        return None

    async def _warmup_ivr_cache(self) -> None:
        """Pre-genere les WAV d'accueil / au revoir pour supprimer l'attente edge-tts a l'appel."""
        settings = self._incoming_settings()
        refresh_modem_voice_assets(self.config, settings)
        greeting = await self._ivr_cache.ensure(self._greeting_text(), "voicemail_greeting")
        goodbye = await self._ivr_cache.ensure(VOICEMAIL_GOODBYE, "voicemail_goodbye")
        if self._is_conversation_mode():
            salutation = await self._ivr_cache.ensure(
                self._conversation_salutation_text(), "kb_salutation"
            )
            if salutation:
                # Croche colle a l'annonce : bip immediat apres la phrase (pas 3s plus tard).
                self._append_talk_cue_to_wav(salutation, gap_ms=220)
                logger.info("IVR pret (conversation): {}", salutation.name)
            self._ensure_talk_cue_wav()
        beep_path = self._ensure_ivr_wav_dir() / "voicemail_beep.wav"
        if not beep_path.is_file() or not beep_path.stat().st_size:
            write_beep_wav_8k(beep_path, profile=getattr(self.modem, "voice_profile", None))
        await self._warmup_track_greeting_cache()
        if greeting:
            logger.info("IVR pret: {}", greeting.name)
        if goodbye:
            logger.info("IVR pret: {}", goodbye.name)
        logger.info("IVR pret: {}", beep_path.name)
        self._refresh_early_greeting_wav()

    async def regenerate_greeting_cache(
        self,
        audio_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Force la regeneration complete du cache accueil (voix + mix) pour le modem.

        Utilise la meme logique que l'apercu UI (TTS + mix intro selon le mode).

        @param audio_override Patch audio formulaire (meme si non sauvegarde).
        @returns Metadonnees du fichier actif (nom, duree, voix TTS).
        """
        from backend.services.greeting_audio_service import (
            _build_modem_greeting_wav_sync,
            _merge_audio_settings,
            _write_greeting_modem_active_meta,
            greeting_modem_active_wav_path,
            try_remote_greeting_mix,
        )

        self.reload_incoming_policy()
        settings = _merge_audio_settings(
            load_incoming_call_settings(self.config),
            audio_override,
        )
        apply_incoming_call_settings(self.config, settings)
        if hasattr(self, "incoming_policy"):
            self.incoming_policy.settings = settings

        greeting = greeting_text(self.config, settings)
        ivr_dir = self._ensure_ivr_wav_dir()
        for pattern in (
            "voicemail_greeting.*",
            "greeting_track_*.wav",
            "greeting_seq_*.wav",
            "greeting_modem_active.*",
        ):
            for path in ivr_dir.glob(pattern):
                try:
                    path.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("Suppression cache {}: {}", path.name, exc)

        active_path = greeting_modem_active_wav_path(self.config)
        remote = await try_remote_greeting_mix(
            self.config,
            settings,
            greeting,
            out_path=active_path,
            output="modem",
        )
        if remote is None:
            voice_wav = await self._ivr_cache.ensure(greeting, "voicemail_greeting")
            if not voice_wav or not voice_wav.is_file():
                raise RuntimeError("Generation TTS accueil echouee")

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: _build_modem_greeting_wav_sync(
                    self.config,
                    settings,
                    voice_wav,
                    out_modem=active_path,
                ),
            )
        else:
            # Garde aussi un cache voix seule pour les replays sans intro.
            await self._ivr_cache.ensure(greeting, "voicemail_greeting")

        if not active_path.is_file() or active_path.stat().st_size < 2000:
            raise RuntimeError("Mix accueil modem vide ou absent")

        regenerated_at = _write_greeting_modem_active_meta(self.config, settings, greeting)
        await self._ivr_cache.ensure(VOICEMAIL_GOODBYE, "voicemail_goodbye")
        beep_path = ivr_dir / "voicemail_beep.wav"
        write_beep_wav_8k(beep_path, profile=getattr(self.modem, "voice_profile", None))
        self._refresh_early_greeting_wav()

        duration = None
        try:
            with wave.open(str(active_path), "rb") as wf:
                rate = wf.getframerate()
                if rate > 0:
                    duration = round(wf.getnframes() / float(rate), 2)
        except (OSError, wave.Error):
            duration = None

        logger.info(
            "Cache accueil modem regenere: {} ({} octets, intro={})",
            active_path.name,
            active_path.stat().st_size,
            getattr(settings.audio, "greeting_intro_mode", "none"),
        )
        return {
            "track_wav": active_path.name,
            "voice_wav": "voicemail_greeting.wav",
            "duration_sec": duration,
            "voice": getattr(self.config, "edge_tts_voice", "") or "",
            "pitch": getattr(self.config, "edge_tts_pitch", "") or "",
            "rate": getattr(self.config, "edge_tts_rate", "") or "",
            "text": greeting,
            "regenerated_at": regenerated_at,
        }

    async def _warmup_track_greeting_cache(self) -> None:
        """
        Pre-construit le mix musique + voix (mode track) pour eviter 20-30 s de silence au 1er appel.

        Le fichier est le meme que celui utilise par ``_play_greeting_sequence``.
        """
        audio = self._audio_settings()
        intro_mode = str(getattr(audio, "greeting_intro_mode", "none") or "none")
        if intro_mode != "track":
            return
        intro = greeting_intro_path(self.config, audio)
        if not intro or not intro.is_file():
            logger.warning("Warmup track: piste absente ({})", intro)
            return
        greeting = self._greeting_text()
        voice_wav = await self._resolve_greeting_modem_wav(greeting, audio)
        if not voice_wav or not voice_wav.is_file():
            logger.warning("Warmup track: voix accueil indisponible")
            return
        intro_ms = int(float(getattr(audio, "greeting_intro_sec", 2.0) or 2.0) * 1000)
        crossfade_ms = int(float(getattr(audio, "greeting_intro_crossfade_ms", 450) or 450))
        music_offset_ms = int(
            float(getattr(audio, "greeting_intro_music_offset_sec", 0.0) or 0.0) * 1000
        )
        track_duck_db = float(getattr(audio, "greeting_intro_track_duck_db", 0.0) or 0.0)
        voice_gain = float(getattr(audio, "greeting_intro_voice_gain_db", 0.0) or 0.0)
        combined = self._track_greeting_cache_path(intro, audio, greeting)
        if not self._track_greeting_cache_stale(combined, intro, voice_wav):
            logger.info("Warmup track deja present: {}", combined.name)
            self._refresh_early_greeting_wav()
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: combine_music_track_voice_overlay(
                    intro,
                    voice_wav,
                    combined,
                    music_solo_ms=intro_ms,
                    music_offset_ms=music_offset_ms,
                    voice_fade_ms=crossfade_ms,
                    music_duck_db=track_duck_db if track_duck_db > 0.5 else None,
                    voice_mix_gain_db=voice_gain,
                ),
            )
            logger.info("Warmup track pret: {}", combined.name)
        except Exception as exc:
            logger.warning("Warmup track echoue: {}", exc)
        self._refresh_early_greeting_wav()
    
    async def run(self):
        """Lance la boucle principale de gestion des appels"""
        self.is_running = True
        
        # Vérifier si le modem est initialisé
        if not self.modem.is_initialized:
            logger.info("Modem non disponible - surveillance des appels désactivée")
            # Attendre indéfiniment pour garder la tâche active
            while self.is_running:
                await asyncio.sleep(60)  # Attendre 1 minute avant de vérifier à nouveau
        else:
            logger.info("Démarrage de la surveillance des appels...")
            # Lancer la surveillance du modem dans une tâche séparée
            await self.modem.monitor_calls()
    
    def _apply_modem_runtime_options(self) -> None:
        """Copie les options config vers le ModemHandler (gains, pays, VDR, PCW)."""
        m = self.modem
        vgr = getattr(self.config, "modem_voice_vgr", None)
        vgt = getattr(self.config, "modem_voice_vgt", None)
        try:
            m.voice_vgr = int(vgr) if vgr is not None and str(vgr).strip() != "" else None
        except (TypeError, ValueError):
            m.voice_vgr = None
        try:
            m.voice_vgt = int(vgt) if vgt is not None and str(vgt).strip() != "" else None
        except (TypeError, ValueError):
            m.voice_vgt = None
        gci = getattr(self.config, "modem_country_gci", None)
        m.modem_country_gci = str(gci).strip() if gci else None
        m.enable_distinctive_ring = bool(getattr(self.config, "modem_distinctive_ring", False))
        m.enable_pcw_off_for_cid = bool(getattr(self.config, "modem_pcw_off_for_cid", True))
        m.preferred_vsm = getattr(self.config, "modem_voice_vsm", None)
        try:
            m.instant_seize_cid_grace_sec = float(
                getattr(self.config, "instant_seize_cid_grace_sec", 0.35) or 0.35
            )
        except (TypeError, ValueError):
            m.instant_seize_cid_grace_sec = 0.35
        self._refresh_instant_ring_seize()

    def _refresh_instant_ring_seize(self) -> None:
        """
        Active le seize sync au RING si repondeur coupe-sonnerie (rings<=0).

        rings=-1 : coupe max (grace CID 0, seize des metas DATE/NMBR si possible).
        """
        auto = bool(getattr(self.config, "incoming_auto_answer", True))
        raw_rings = getattr(self.config, "rings_before_answer", 0)
        try:
            min_answer_rings = int(raw_rings) if raw_rings is not None else 0
        except (TypeError, ValueError):
            min_answer_rings = 0
        whitelist_ring_only = bool(getattr(self.config, "whitelist_ring_only", False))
        answer_rings: list[int] = []
        try:
            if hasattr(self, "incoming_policy"):
                for profile in ("screened", "blocked", "permitted"):
                    resolved = resolve_profile_decision(
                        self.incoming_policy.settings, profile
                    )
                    if "answer" in resolved.actions:
                        answer_rings.append(int(resolved.rings_before_answer))
                if answer_rings:
                    min_answer_rings = min(answer_rings)
        except Exception:
            pass
        self.modem.instant_ring_seize = bool(
            auto and min_answer_rings <= 0 and not whitelist_ring_only
        )
        # -1 = agressif : pas d'attente CID avant VLS.
        if min_answer_rings < 0:
            self.modem.instant_seize_cid_grace_sec = 0.0
            self.modem.pre_ring_seize_on_cid_meta = True
            self.modem.ultra_fast_seize = True
        else:
            try:
                self.modem.instant_seize_cid_grace_sec = float(
                    getattr(self.config, "instant_seize_cid_grace_sec", 0.35) or 0.35
                )
            except (TypeError, ValueError):
                self.modem.instant_seize_cid_grace_sec = 0.35
            self.modem.pre_ring_seize_on_cid_meta = False
            self.modem.ultra_fast_seize = False
        logger.info(
            "instant_ring_seize={} (auto_answer={}, min_answer_rings={}, whitelist_ring_only={})",
            self.modem.instant_ring_seize,
            auto,
            min_answer_rings,
            whitelist_ring_only,
        )
        self._refresh_early_greeting_wav()

    def _incoming_settings(self):
        """Settings incoming_call en memoire (policy ou YAML)."""
        if hasattr(self, "incoming_policy"):
            return self.incoming_policy.settings
        return load_incoming_call_settings(self.config)

    def _resolve_early_greeting_wav_path(self) -> Optional[Path]:
        """
        WAV d'accueil pre-genere pour lecture immediate au seize (sync, sans TTS).

        @returns Chemin cache actif modem, track ou voicemail_greeting.
        """
        from backend.services.greeting_audio_service import (
            greeting_modem_active_wav_path,
            is_greeting_modem_active_fresh,
        )

        settings = self._incoming_settings()
        # Mode conversation : meme ouverture que le tchat KB (pas le message repondeur).
        if self._is_conversation_mode():
            conv = self._conversation_greeting_wav()
            if conv is not None:
                return conv
        greeting = greeting_text(self.config, settings)
        active = greeting_modem_active_wav_path(self.config)
        if active.is_file() and active.stat().st_size >= 4000:
            if is_greeting_modem_active_fresh(self.config, settings, greeting):
                return active
            logger.warning(
                "Cache accueil modem perime — lecture du mix existant ({})",
                active.name,
            )
            return active

        audio = settings.audio
        intro_mode = str(getattr(audio, "greeting_intro_mode", "none") or "none")
        if intro_mode == "track":
            intro = greeting_intro_path(self.config, audio)
            if intro and intro.is_file():
                combined = self._track_greeting_cache_path(intro, audio, greeting)
                if combined.is_file() and combined.stat().st_size >= 2000:
                    return combined
            return None
        cached = self._ivr_cache.get_if_fresh(greeting, "voicemail_greeting")
        if cached and cached.is_file():
            return cached
        return None

    def _refresh_early_greeting_wav(self) -> None:
        """Pousse le WAV accueil cache vers le modem (si seize immediat actif)."""
        if not getattr(self.modem, "set_early_greeting_wav", None):
            return
        path = self._resolve_early_greeting_wav_path()
        enabled = bool(getattr(self.modem, "instant_ring_seize", False))
        self.modem.set_early_greeting_wav(path, enabled=enabled)
        if path:
            logger.info("Accueil immediat configure: {} (enabled={})", path.name, enabled)
        else:
            logger.debug("Accueil immediat: pas de WAV cache pret")

    def _seed_recorder_with_early_greeting(self, recorder: "_IncomingLineRecorder") -> None:
        """
        Recolle l'accueil post-seize dans l'enregistrement d'appel.

        Pendant VTX l'audio n'est pas capturable en VRX : on injecte le WAV joué,
        converti au profil modem actif (evite seed 11 kHz compte en 8 kHz → SRT
        decale de 11 s, appel #53).

        @param recorder Enregistreur ligne a alimenter.
        """
        path = getattr(self.modem, "early_greeting_wav", None)
        if not path:
            return
        wav_path = Path(path)
        if not wav_path.is_file():
            return
        try:
            from backend.voice.audio_utils import wav_path_to_modem_pcm

            profile = getattr(self.modem, "voice_profile", None)
            pcm = wav_path_to_modem_pcm(
                wav_path,
                profile=profile,
                normalize=False,
            )
            if pcm:
                recorder.append_pcm(pcm)
                recorder.mark_seed_pcm(pcm)
                self._log_call(
                    "record_seed_accueil",
                    octets=len(pcm),
                    dur_s=round(recorder.seed_duration_sec(), 2),
                )
        except Exception as exc:
            logger.warning("Seed accueil enregistrement: {}", exc)

    def reload_incoming_policy(self) -> None:
        """
        Recharge incoming_call_settings + policy apres PATCH API settings.

        Reapplique aussi instant_ring_seize sur le modem.
        """
        settings = load_incoming_call_settings(self.config)
        apply_incoming_call_settings(self.config, settings)
        if hasattr(self, "incoming_policy"):
            self.incoming_policy.reload()
        self._refresh_instant_ring_seize()
        self._refresh_early_greeting_wav()

    def _arm_call_deadline(self) -> None:
        """Pose une deadline wall-clock pour max_call_duration."""
        import time as _time

        max_sec = int(getattr(self.config, "max_call_duration", 300) or 300)
        self._call_deadline = _time.monotonic() + max(30, max_sec)

    def _call_deadline_exceeded(self) -> bool:
        import time as _time

        return bool(self._call_deadline and _time.monotonic() >= self._call_deadline)

    async def _wait_phone_mode_rings_end(self, *, max_wait_sec: float) -> str:
        """
        Mode telephone : attend la fin des RING (ou timeout).

        @returns ``answered_elsewhere`` si plus de RING longtemps, ``timeout`` sinon.
        """
        import time as _time

        self._phone_mode_ring_event = asyncio.Event()
        self._last_ring_seen = _time.monotonic()
        deadline = _time.monotonic() + max_wait_sec
        quiet_sec = float(
            getattr(
                getattr(self, "incoming_policy", None),
                "settings",
                None,
            ).ring_quiet_abort_sec
            if getattr(self, "incoming_policy", None) is not None
            else 6.0
        )
        if quiet_sec <= 0:
            quiet_sec = 6.0
        while _time.monotonic() < deadline:
            if self._phone_mode_ring_event.is_set():
                self._phone_mode_ring_event.clear()
                self._last_ring_seen = _time.monotonic()
            elif (_time.monotonic() - self._last_ring_seen) >= quiet_sec:
                return "answered_elsewhere"
            await asyncio.sleep(0.4)
        return "timeout"

    async def _wait_for_rings_before_answer(self, target_rings: int) -> bool:
        """
        Attend N sonneries avant decrochage (style Call Attendant).

        @param target_rings Nombre total de RING souhaites avant answer.
        @returns False si le fixe parallele a decroche (silence RING).
        """
        import time as _time

        if target_rings <= 0:
            return True
        quiet_sec = 6.0
        cycle_sec = 6.0
        if hasattr(self, "incoming_policy"):
            quiet_sec = float(
                getattr(self.incoming_policy.settings, "ring_quiet_abort_sec", 6.0) or 6.0
            )
            cycle_sec = float(
                getattr(self.incoming_policy.settings, "ring_cycle_sec", 6.0) or 6.0
            )
        abort_parallel = True
        adv = getattr(getattr(self.incoming_policy, "settings", None), "advanced", None)
        if adv is not None:
            abort_parallel = bool(getattr(adv, "abort_answer_if_parallel_pickup", True))

        deadline = _time.monotonic() + float(target_rings) * cycle_sec + quiet_sec + 5.0
        logger.info(
            "wait_for_rings: entendu={}/{} (quiet={}s)",
            self._call_rings_heard,
            target_rings,
            quiet_sec,
        )
        while _time.monotonic() < deadline:
            if self._call_rings_heard >= target_rings:
                return True
            if abort_parallel and self._call_rings_heard > 0:
                if self._phone_mode_ring_event and self._phone_mode_ring_event.is_set():
                    self._phone_mode_ring_event.clear()
                    self._last_ring_seen = _time.monotonic()
                elif (_time.monotonic() - self._last_ring_seen) >= quiet_sec:
                    logger.info("wait_for_rings: silence — fixe parallele ou fin appel")
                    return False
            await asyncio.sleep(0.3)
        return self._call_rings_heard >= target_rings

    async def _release_line_if_seized(self) -> None:
        """
        Raccroche si un seize sync a eu lieu alors que la policy demande ignore.

        Libere la ligne pour le telephone parallele.
        """
        seized = self.modem.consume_incoming_seize()
        if seized or self._line_already_answered:
            try:
                await self.modem.hangup()
            except Exception:
                pass
        self._line_already_answered = False

    async def _journal_parallel_call(
        self,
        caller_id: Optional[str],
        caller_name: Optional[str],
        *,
        rings: int,
        reason: str,
        decision=None,
    ) -> None:
        """
        Journalise un appel sans repondeur modem (fixe gere la ligne).

        Si ``phone_mode_record`` et decroche parallele : greffe silencieuse +
        enregistrement VRX jusqu'au raccrochage, puis STT final.

        @param caller_id Numero.
        @param caller_name Nom CID.
        @param rings Sonneries configurees pour l'attente.
        @param reason Motif log (policy ignore, mode telephone).
        """
        import time as _time

        call = await self.call_service.create_incoming_call(
            phone_number=caller_id,
            caller_name=caller_name,
        )
        if decision is not None:
            await self.call_service.annotate_incoming_policy(
                call.id,
                profile=decision.profile,
                source=decision.source,
                rings_before_answer=int(decision.rings_before_answer),
                ignored=True,
            )
        self.current_call_id = call.id
        logger.info("{} — pas de ATA (appel #{}), fixe parallele", reason, call.id)
        cycle = 8.0
        if hasattr(self, "incoming_policy"):
            cycle = float(getattr(self.incoming_policy.settings, "ring_cycle_sec", 8.0) or 8.0)
        wait_sec = max(12.0, float(max(rings, 1)) * cycle)
        t0 = _time.monotonic()
        outcome = await self._wait_phone_mode_rings_end(max_wait_sec=wait_sec)
        ring_sec = max(1, int(_time.monotonic() - t0))
        caller_id = self._pending_cid or caller_id
        caller_name = self._pending_cname or caller_name
        if caller_id or caller_name:
            await self.call_service.set_call_caller_info(
                call.id, phone_number=caller_id, caller_name=caller_name
            )

        record = bool(getattr(self.config, "phone_mode_record", True))
        if outcome == "answered_elsewhere" and not record:
            logger.info(
                "Appel #{} repondu ailleurs — phone_mode_record=false, pas d'enregistrement",
                call.id,
            )
        if outcome == "answered_elsewhere" and record:
            joined = False
            try:
                joined = await self.modem.join_line_for_listen()
            except Exception:
                logger.exception("phone_record_join_failed appel #{}", call.id)
            if joined:
                if decision is not None:
                    try:
                        await self.call_service.annotate_incoming_policy(
                            call.id,
                            profile=decision.profile,
                            source=decision.source,
                            rings_before_answer=int(decision.rings_before_answer),
                            ignored=False,
                        )
                    except Exception:
                        pass
                await self._record_phone_parallel_conversation(call.id)
                return
            self._log_call("phone_record_join_failed", call_id=call.id, reason=reason)
            logger.warning(
                "Greffe silencieuse echouee (appel #{}) — journalisation sans audio",
                call.id,
            )

        if outcome == "answered_elsewhere":
            await self.call_service.answer_call(call.id)
            await self.call_service.complete_call(call.id, duration=ring_sec)
            self._log_call(
                "phone_parallel_repondu",
                call_id=call.id,
                duree_sonnerie_s=ring_sec,
            )
            logger.info(
                "Fin journalisation appel #{} (repondu ailleurs, sonnerie ~{}s)",
                call.id,
                ring_sec,
            )
        else:
            await self.call_service.miss_call(call.id)
            self._log_call(
                "phone_parallel_manque",
                call_id=call.id,
                duree_sonnerie_s=ring_sec,
            )
            logger.info(
                "Fin journalisation appel #{} (manque / timeout, sonnerie ~{}s)",
                call.id,
                ring_sec,
            )
        self.current_call_id = None

    async def _save_pcm16_call_wav(self, call_id: int, pcm16: bytes) -> Optional[str]:
        """
        Ecrit un WAV 16 kHz mono pour un appel telephone parallele.

        @param call_id ID appel.
        @param pcm16 PCM s16le 16 kHz.
        @returns Chemin relatif ou None.
        """
        if not pcm16:
            return None
        base = Path(self.config.base_path) if self.config.base_path else Path.cwd()
        recordings_dir = base / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        wav_rel = f"recordings/call_phone_{call_id}_{ts}.wav"
        wav_path = base / wav_rel
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm16)
        await self.call_service.set_audio_file(call_id, wav_rel)
        logger.info("Appel telephone parallele enregistre: {} ({} octets)", wav_rel, len(pcm16))
        return wav_rel

    async def _transcribe_call_async(self, call_id: int, audio_pcm_16k: bytes) -> None:
        """
        Transcrit un enregistrement d'appel (STT) sans bloquer la ligne.

        @param call_id ID de l'appel.
        @param audio_pcm_16k PCM 16 kHz 16-bit mono.
        """
        try:
            text, cues = await self.voice_recognition.transcribe_with_cues(
                audio_pcm_16k, sample_rate=16000
            )
            text = (text or "").strip()
            if not text:
                logger.info("STT appel #{} : vide / inaudible", call_id)
                return
            await self.call_service.set_transcription_and_intent(
                int(call_id), transcription=text, cues=cues or None
            )
            await event_bus.publish(
                Event(
                    event_type=EventType.CALL_TRANSCRIPTION_FINAL,
                    timestamp=datetime.utcnow(),
                    data={"call_id": call_id, "text": text},
                )
            )
            logger.info("STT appel #{} : {}", call_id, text[:120])
        except Exception:
            logger.exception("STT appel #{} echoue", call_id)

    async def _record_phone_parallel_conversation(self, call_id: int) -> None:
        """
        Enregistre la conversation apres greffe silencieuse (VRX continu).

        Utilise ``_IncomingLineRecorder`` (flux VRX permanent) plutot que des
        tranches ``_record_audio`` 1s qui coupaient trop tot. STT final async.
        Release via ATH force (fix ligne OQP).

        @param call_id ID de l'appel deja cree.
        """
        self.current_call_id = call_id
        self._call_db_finalized = False
        self._line_already_answered = True
        self._arm_call_deadline()
        self._active_call_monotonic = time.monotonic()
        await self.call_service.answer_call(call_id)
        self._log_call("phone_record_debut", call_id=call_id)

        max_sec = int(getattr(self.config, "max_call_duration", 300) or 300)
        recorder = _IncomingLineRecorder(self)
        self._incoming_recorder = recorder
        pcm_all = b""
        stop_reason = "ok"
        try:
            await recorder.start(already_in_voice_mode=self._use_modem_voice_serial())
            if not recorder._session:
                stop_reason = "vrx_open_failed"
                logger.warning("phone_record: VRX non ouvert (appel #{})", call_id)
            else:
                deadline = time.monotonic() + max(30, max_sec)
                last_bytes = 0
                idle_since: Optional[float] = None
                while time.monotonic() < deadline and self._call_still_active(call_id):
                    await asyncio.sleep(0.35)
                    raw_tail = b"".join(recorder.chunks[-30:]) if recorder.chunks else b""
                    if raw_tail and _vrx_buffer_has_hangup_marker(raw_tail):
                        stop_reason = "hangup_marker"
                        break
                    cur = sum(len(c) for c in recorder.chunks)
                    if cur > last_bytes:
                        last_bytes = cur
                        idle_since = None
                    else:
                        if idle_since is None:
                            idle_since = time.monotonic()
                        elif last_bytes > 4000 and (time.monotonic() - idle_since) >= 20.0:
                            stop_reason = "vrx_idle"
                            break
                if time.monotonic() >= deadline and stop_reason == "ok":
                    stop_reason = "max_duration"

            await recorder.pause()
            modem_pcm = b"".join(recorder.chunks)
            if modem_pcm:
                profile = self.modem.voice_profile
                peak = pcm_chunk_peak(modem_pcm, sample_width=profile.sample_width)
                logger.info(
                    "phone_record modem PCM: {} o peak={} rate={} width={}",
                    len(modem_pcm),
                    peak,
                    profile.sample_rate,
                    profile.sample_width,
                )
                pcm_all = pcm_modem_to_s16le_16k(modem_pcm, profile)
            self._log_call(
                "phone_record_vrx_fin",
                call_id=call_id,
                octets=len(pcm_all or b""),
                raison=stop_reason,
            )
        except Exception:
            logger.exception("phone_record erreur appel #{}", call_id)
            stop_reason = "exception"
            try:
                await recorder.pause()
            except Exception:
                pass
        finally:
            self._incoming_recorder = None
            if pcm_all:
                try:
                    await self._save_pcm16_call_wav(call_id, pcm_all)
                except Exception:
                    logger.exception("Sauvegarde WAV phone #{} echouee", call_id)
                if self._recognition_available or getattr(self.config, "stt_service_url", None):
                    asyncio.create_task(
                        self._transcribe_call_async(call_id, pcm_all),
                        name=f"stt_phone_{call_id}",
                    )
            else:
                logger.warning(
                    "phone_record appel #{} : aucun PCM (raison={})",
                    call_id,
                    stop_reason,
                )
            if self._active_call_monotonic is not None:
                self._pending_call_duration_sec = max(
                    1, int(time.monotonic() - self._active_call_monotonic)
                )
            duration = self._pending_call_duration_sec
            await self.release_active_call(
                reason="phone_record_fin",
                complete=True,
                call_id=call_id,
            )
            self._log_call(
                "phone_record_fin",
                call_id=call_id,
                octets=len(pcm_all or b""),
                duration=duration or 0,
                raison=stop_reason,
            )

    async def handle_incoming_call(self, caller_id: Optional[str] = None, caller_name: Optional[str] = None):
        """
        Traite un appel entrant.

        Attend le Caller ID (NMBR=/NAME=) pendant une fenetre courte avant de
        decrocher. La surveillance modem continue en parallele (callbacks en
        tache) pour ne pas rater NMBR= entre deux RING.

        Args:
            caller_id: Numéro de téléphone de l'appelant
            caller_name: Nom de l'appelant (si disponible)
        """
        caller_id = normalize_cid_value(caller_id)
        caller_name = normalize_cid_value(caller_name)

        if caller_id:
            self._pending_cid = caller_id
            if self._cid_event:
                self._cid_event.set()
        if caller_name:
            self._pending_cname = caller_name
            if self._cname_event:
                self._cname_event.set()
            if self._cid_event and self._pending_cid:
                self._cid_event.set()

        # RING supplementaires (mode telephone ou wait_for_rings).
        if self._incoming_handling:
            self._call_rings_heard += 1
            if self._phone_mode_ring_event is not None and not caller_id and not caller_name:
                self._phone_mode_ring_event.set()
            self._last_ring_seen = time.monotonic()

        if self._incoming_handling:
            if (caller_id or caller_name) and self.current_call_id:
                await self.call_service.set_call_caller_info(
                    self.current_call_id,
                    phone_number=caller_id,
                    caller_name=caller_name,
                )
            return

        # Flag avant tout await : evite deux handlers RING en parallele.
        self._incoming_handling = True
        self._line_already_answered = False
        self._call_rings_heard = 1
        import time as _time

        self._last_ring_seen = _time.monotonic()
        self._phone_mode_ring_event = asyncio.Event()
        self._cid_event = asyncio.Event()
        self._cname_event = asyncio.Event()
        if caller_id:
            self._pending_cid = caller_id
            self._cid_event.set()
        if caller_name:
            self._pending_cname = caller_name
            self._cname_event.set()
        logger.info("Appel entrant de {} ({})", caller_id, caller_name)
        self._log_call("ring_debut", caller=caller_id or "?", name=caller_name or "-")

        try:
            auto_answer_cfg = apply_schedule_to_auto_answer(self.config)
            raw_rings = getattr(self.config, "rings_before_answer", 0)
            try:
                rings = int(raw_rings) if raw_rings is not None else 0
            except (TypeError, ValueError):
                rings = 0
            cut_max = rings < 0
            if cut_max:
                rings = 0
            whitelist_ring_only = bool(getattr(self.config, "whitelist_ring_only", False))
            cid_wait = float(getattr(self.config, "cid_wait_sec", 2.5) or 2.5)
            timed_out = False

            need_cid_before_action = (
                not auto_answer_cfg
                or rings > 0
                or (auto_answer_cfg and whitelist_ring_only)
            )
            # rings=-1 / 0 : pas d'attente CID avant decision (modale plus tot).
            immediate_answer = bool(
                auto_answer_cfg
                and rings <= 0
                and (cut_max or not need_cid_before_action)
            )
            if immediate_answer:
                timeout_sec = 0.0
            elif rings > 0:
                timeout_sec = max(cid_wait, float(rings) * 6.0)
            else:
                timeout_sec = max(1.2, cid_wait)

            if timeout_sec > 0 and not self._pending_cid:
                logger.info(
                    "Attente Caller ID jusqu a {:.1f}s avant decision (rings={})",
                    timeout_sec,
                    rings,
                )
                try:
                    await asyncio.wait_for(self._cid_event.wait(), timeout=timeout_sec)
                except asyncio.TimeoutError:
                    timed_out = True
                    logger.info("Pas de Caller ID apres {:.1f}s", timeout_sec)
            elif timeout_sec > 0 and self._pending_cid and not self._pending_cname:
                try:
                    await asyncio.wait_for(self._cname_event.wait(), timeout=0.6)
                except asyncio.TimeoutError:
                    pass
            elif immediate_answer:
                logger.info("Repondeur: decrochage immediat (rings=0, pas d'attente CID)")

            caller_id = self._pending_cid or caller_id
            caller_name = self._pending_cname or caller_name
            cause = classify_cid_outcome(
                caller_id=caller_id,
                source="ring",
                timed_out=timed_out,
            )
            logger.info(
                "CID decision cause={} id={} name={} raw={}",
                cause,
                caller_id,
                caller_name,
                getattr(self.modem, "last_cid_raw", None),
            )

            decision = await self.incoming_policy.resolve_async(
                self.block_service,
                caller_id=caller_id,
                caller_name=caller_name,
            )
            self._current_incoming_decision = decision
            rings = int(decision.rings_before_answer)
            if rings < 0 or cut_max:
                cut_max = True
                rings = 0
            auto_answer = bool(auto_answer_cfg and decision.should_answer)
            logger.info(
                "Policy: profile={} source={} ignore={} answer={} rings={} actions={}",
                decision.profile,
                decision.source,
                decision.should_ignore,
                decision.should_answer,
                rings,
                decision.actions,
            )

            if decision.should_ignore or not auto_answer:
                await self._release_line_if_seized()
                await self._journal_parallel_call(
                    caller_id,
                    caller_name,
                    rings=rings if decision.should_ignore else rings,
                    reason=(
                        f"policy:{decision.profile}"
                        if decision.should_ignore
                        else "incoming_auto_answer=false"
                    ),
                    decision=decision,
                )
                return

            if rings > 0:
                ok_rings = await self._wait_for_rings_before_answer(rings)
                if not ok_rings:
                    await self._release_line_if_seized()
                    await self._journal_parallel_call(
                        caller_id,
                        caller_name,
                        rings=rings,
                        reason="parallel_pickup_before_rings",
                        decision=decision,
                    )
                    return

            # PRIORITE: couper la sonnerie (souvent deja fait en sync au RING).
            seized = self.modem.consume_incoming_seize()
            ata_cid, ata_cname = None, None
            if seized is not None:
                ok = bool(seized)
                self._log_call("seize_sync_ring", ok=int(ok))
                logger.info("Repondeur: seize sync deja fait au RING (ok={})", ok)
                if not ok:
                    ok, ata_cid, ata_cname = await self.modem.answer_call(fast_voice_seize=True)
            else:
                fast_seize = rings <= 0 and auto_answer and self.modem.supports_voice_serial
                self._log_call("seize_answer", fast=int(fast_seize), rings=rings)
                ok, ata_cid, ata_cname = await self.modem.answer_call(fast_voice_seize=fast_seize)
            self._log_call("seize_fin", ok=int(ok))
            if ok and auto_answer and rings <= 0 and not getattr(self.modem, "_voice_line_ready", False):
                await self.modem.prepare_voice_line_after_seize()
            self._line_already_answered = ok
            if not caller_id and ata_cid:
                caller_id = normalize_cid_value(ata_cid)
                logger.info("CID via ATA: {}", caller_id)
            if not caller_name and ata_cname:
                caller_name = normalize_cid_value(ata_cname)
            caller_id = self._pending_cid or caller_id
            caller_name = self._pending_cname or caller_name

            # UI temps reel apres seize (ne doit pas retarder VLS=1).
            call = await self.call_service.create_incoming_call(
                phone_number=caller_id,
                caller_name=caller_name,
            )
            self.current_call_id = call.id
            self._call_db_finalized = False
            self._pending_call_duration_sec = None
            self._arm_call_deadline()
            self._log_call(
                "call_cree",
                db_id=call.id,
                profile=decision.profile,
                seize_ok=int(ok),
            )
            await self.call_service.annotate_incoming_policy(
                call.id,
                profile=decision.profile,
                source=decision.source,
                rings_before_answer=int(decision.rings_before_answer),
                ignored=False,
            )
            if caller_id or caller_name:
                await self.call_service.set_call_caller_info(
                    call.id, phone_number=caller_id, caller_name=caller_name
                )

            if not ok:
                logger.error(
                    "Impossible de decrocher au RING — on laisse le fixe, pas de message d'accueil"
                )
                try:
                    await self.modem.hangup()
                except Exception:
                    pass
                await self.call_service.miss_call(call.id)
                self.current_call_id = None
                return

            is_blocked = decision.profile == "blocked"

            if is_blocked:
                self._log_call("branche_bloque", caller=caller_id or "?")
                logger.info("Appel bloqué: {}", caller_id)
                await self.call_service.block_call(call.id)
                await self._handle_blocked_call(skip_answer=True)
            else:
                self._log_call("branche_autorise", caller=caller_id or "?")
                self._active_call_monotonic = time.monotonic()
                await self.call_service.answer_call(call.id)
                await self._handle_permitted_call(skip_modem_answer=True, line_answered=ok)

        except Exception as e:
            logger.exception("Erreur lors du traitement de l'appel: {}", e)
            await self.release_active_call(reason="incoming_exception", complete=False)
        finally:
            self._log_call("ring_fin")
            self._incoming_handling = False
            self._line_already_answered = False
            self._pending_cid = None
            self._pending_cname = None
            self._cid_event = None
            self._cname_event = None
            self._phone_mode_ring_event = None
            self._call_deadline = None
            self._current_incoming_decision = None
            if self.current_call_id:
                await self.release_active_call(reason="incoming_finally", complete=True)
            else:
                try:
                    self.modem.clear_incoming_seize()
                except Exception:
                    pass
    
    async def _handle_blocked_call(self, skip_answer: bool = False):
        """Traite un appel bloqué"""
        logger.info("Traitement d'un appel bloqué")
        
        try:
            if not skip_answer:
                ok, _cid, _cname = await self.modem.answer_call()
                if not ok:
                    logger.warning("Impossible de decrocher pour message bloque")
            settings = (
                self.incoming_policy.settings
                if hasattr(self, "incoming_policy")
                else load_incoming_call_settings(self.config)
            )
            audio = settings.audio
            await self._play_configured_message(
                source=audio.blocked_source,
                wav_path=audio.blocked_wav_path,
                tts_text=blocked_message_text(settings),
                fallback_text="Desole, cet appel a ete bloque.",
                already_in_voice_mode=self._use_modem_voice_serial() and skip_answer,
            )
        
        except Exception as e:
            logger.exception(f"Erreur lors du traitement d'un appel bloqué: {e}")
        finally:
            call_id = self.current_call_id
            await self.release_active_call(
                reason="blocked_finally",
                complete=True,
                call_id=call_id,
            )
    
    async def _handle_permitted_call(
        self,
        skip_modem_answer: bool = False,
        *,
        line_answered: bool = True,
    ):
        """Traite un appel autorisé"""
        tracked_call_id = self.current_call_id
        self._log_call("autorise_debut")
        recorder = _IncomingLineRecorder(self)
        self._incoming_recorder = recorder
        self._skip_incoming_recording_save = False

        try:
            ok = bool(line_answered) if skip_modem_answer else False
            caller_id, caller_name = None, None
            if not skip_modem_answer:
                ok, caller_id, caller_name = await self.modem.answer_call()
            if not ok:
                logger.error("Impossible de décrocher")
                if self.current_call_id:
                    await self.call_service.miss_call(self.current_call_id)
                return
            if self.current_call_id and (caller_id or caller_name):
                await self.call_service.set_call_caller_info(
                    self.current_call_id,
                    phone_number=caller_id,
                    caller_name=caller_name,
                )

            greeting = self._greeting_text()
            audio = self._audio_settings()
            conversation_mode = self._is_conversation_mode()
            early_mode = bool(getattr(self.modem, "early_greeting_was_scheduled", lambda: False)())
            await self.modem.wait_early_greeting_done()
            played = bool(getattr(self.modem, "_greeting_played_on_seize", False))
            interrupted = bool(getattr(self.modem, "_playback_interrupted", False))
            if interrupted:
                self._log_call(
                    "accueil_interrompu",
                    interrupted=1,
                    played=int(played),
                    raison="raccrochage_pendant_annonce",
                )
                logger.info("Appelant a raccroche pendant l'accueil — pas de repondeur")
                return

            # Accueil VTX fini : demarre l'enregistrement ligne tout de suite (seize).
            # L'accueil early n'est pas capturable en VRX → on le recolle depuis le WAV.
            if self._use_modem_voice_serial():
                if played:
                    self._seed_recorder_with_early_greeting(recorder)
                await recorder.start(already_in_voice_mode=True)
                self._log_call(
                    "record_start_seize",
                    session=int(bool(recorder._session)),
                    seed_accueil=int(bool(played)),
                )

            if played:
                self._log_call("accueil_deja_joue")
                logger.info(
                    "Accueil deja joue au seize — suite {}",
                    "conversation" if conversation_mode else "repondeur",
                )
            elif early_mode:
                if not played:
                    logger.warning("Accueil immediat echoue — un seul reessai apres reprise ligne")
                    self.modem._playback_interrupted = False
                    self.modem._voice_abort = False
                    await self.modem.prepare_voice_line_after_seize()
                    if conversation_mode:
                        played = await self._play_conversation_opening(
                            already_in_voice_mode=True,
                            recorder=recorder,
                        )
                    else:
                        played = await self._play_greeting_sequence(
                            greeting=greeting,
                            audio=audio,
                            already_in_voice_mode=True,
                            recorder=recorder,
                        )
                    interrupted = bool(getattr(self.modem, "_playback_interrupted", False))
            else:
                if conversation_mode:
                    played = await self._play_conversation_opening(
                        already_in_voice_mode=True,
                        recorder=recorder,
                    )
                else:
                    played = await self._play_greeting_sequence(
                        greeting=greeting,
                        audio=audio,
                        already_in_voice_mode=True,
                        recorder=recorder,
                    )
                interrupted = bool(getattr(self.modem, "_playback_interrupted", False))
            if not played and skip_modem_answer and not early_mode and not interrupted:
                logger.warning("Accueil echoue apres seize — reprise ligne voix puis nouvel essai")
                await self.modem.prepare_voice_line_after_seize()
                if conversation_mode:
                    played = await self._play_conversation_opening(
                        already_in_voice_mode=True,
                        recorder=recorder,
                    )
                else:
                    played = await self._play_greeting_sequence(
                        greeting=greeting,
                        audio=audio,
                        already_in_voice_mode=True,
                        recorder=recorder,
                    )
                interrupted = bool(getattr(self.modem, "_playback_interrupted", False))
            if interrupted or played is False:
                self._log_call(
                    "accueil_interrompu",
                    interrupted=int(interrupted),
                    played=int(bool(played)),
                )
                logger.info("Accueil interrompu (tel parallele / hangup) — fin sans repondeur")
                return

            if self._call_deadline_exceeded():
                self._log_call("deadline_depasse")
                logger.warning("max_call_duration atteint juste apres accueil")
                return

            vm_settings = self._voicemail_settings()
            vm_mode = (
                getattr(vm_settings, "mode", None)
                or getattr(self.config, "voicemail_mode", "simple")
                or "simple"
            )
            vm_mode = str(vm_mode).strip().lower()

            if self.config.voicemail_enabled:
                decision = getattr(self, "_current_incoming_decision", None)
                if self._needs_dtmf_gate(decision):
                    if not await self._run_dtmf_gate():
                        logger.info("Filtre DTMF non valide — fin sans enregistrement")
                        return
                if vm_mode == "ivr" and self._recognition_available:
                    await self._handle_voice_interaction(recorder=recorder)
                elif vm_mode == "conversation":
                    if not self._recognition_available:
                        logger.warning(
                            "voicemail_mode=conversation mais STT indisponible — "
                            "repli repondeur simple"
                        )
                        self._log_call("repondeur_conversation_fallback_simple")
                        await self._handle_voicemail_simple(
                            recorder=recorder,
                            skip_beep=bool(played),
                        )
                    else:
                        self._log_call("repondeur_conversation")
                        await self._handle_voicemail_conversation(
                            recorder=recorder,
                            skip_beep=bool(played),
                        )
                else:
                    self._log_call("repondeur_simple")
                    # Bip deja dans greeting_modem_active (500 ms apres le message).
                    await self._handle_voicemail_simple(
                        recorder=recorder,
                        skip_beep=bool(played),
                    )
            else:
                await self._record_message(recorder=recorder)

        except Exception as e:
            logger.exception("Erreur lors du traitement d'un appel autorisé: %s", e)
            await self._play_on_line(
                "Désolé, une erreur s'est produite. Au revoir.",
                already_in_voice_mode=True,
                recorder=recorder,
            )
        finally:
            call_id = tracked_call_id or self.current_call_id
            if call_id and not self._skip_incoming_recording_save:
                try:
                    await recorder.save(call_id)
                except Exception as exc:
                    logger.warning("Sauvegarde enregistrement entrant: {}", exc)
            elif call_id and self._skip_incoming_recording_save:
                self._log_call("record_ignore", raison="pas_de_message")
            if call_id is not None:
                await self.release_active_call(
                    reason="permitted_finally",
                    complete=True,
                    call_id=call_id,
                )
            self._incoming_recorder = None
            self._skip_incoming_recording_save = False
    
    async def _handle_voicemail_simple(
        self,
        recorder: Optional[_IncomingLineRecorder] = None,
        *,
        skip_beep: bool = False,
    ):
        """
        Répondeur classique : bip, enregistrement avec détection raccrochage / silence, message de fin.

        Le PCM apres le bip est aussi sauve dans ``messages/`` + table ``voicemails``
        (separe de l enregistrement global de l appel qui peut contenir l accueil).

        @param recorder Enregistreur parallèle entrant (optionnel).
        @param skip_beep True si le bip a déjà été joué juste après le message d'accueil.
        """
        vm = self._voicemail_settings()
        max_duration = int(vm.max_record_sec or self.config.voicemail_max_duration)
        silence_sec = float(
            vm.silence_end_sec
            or getattr(self.config, "voicemail_silence_timeout_sec", 3)
            or 3
        )
        logger.info("Mode répondeur simple (bip + enregistrement)")
        self._log_call("repondeur_debut", max_sec=max_duration, silence_sec=silence_sec)
        rec = recorder or self._incoming_recorder
        try:
            if not skip_beep:
                await self._play_beep_on_line(recorder=rec)

            base = Path(self.config.base_path) if self.config.base_path else Path.cwd()
            messages_dir = base / "messages"
            messages_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            call_id = self.current_call_id or 0
            wav_rel = f"messages/vm_{call_id}_{ts}.wav"
            persist_path = base / wav_rel
            active_call_id = call_id

            audio_data = await self._record_audio(
                duration=max_duration,
                already_in_voice_mode=self._use_modem_voice_serial(),
                recorder=rec,
                stop_on_remote_hangup=True,
                silence_timeout_sec=silence_sec,
                persist_wav=persist_path,
            )
            if not self._call_still_active(active_call_id):
                self._log_call("repondeur_annule", raison="release_pendant_enregistrement")
                if persist_path.exists():
                    try:
                        persist_path.unlink()
                    except OSError:
                        pass
                return

            if audio_data:
                logger.info("Message répondeur capturé (%s octets PCM STT)", len(audio_data))

            heard_speech = bool(getattr(self.modem, "last_vrx_heard_speech", False))
            if persist_path.exists() and persist_path.stat().st_size >= 4000 and heard_speech:
                duration_sec = 1
                try:
                    with wave.open(str(persist_path), "rb") as wf:
                        rate = float(wf.getframerate() or 1)
                        duration_sec = max(1, int(wf.getnframes() / rate))
                except Exception:
                    bps = max(1, int(self.modem.voice_profile.bytes_per_sec))
                    duration_sec = max(1, int(persist_path.stat().st_size / bps))
                phone = None
                cname = None
                call_row = self.call_service.call_repo.get_by_id(active_call_id)
                if call_row:
                    phone = call_row.phone_number
                    cname = call_row.caller_name
                vm = await self.call_service.save_voicemail(
                    wav_rel,
                    call_id=active_call_id,
                    phone_number=phone,
                    caller_name=cname,
                    duration=duration_sec,
                )
                # STT en arriere-plan (Vosk/Whisper) pour ne pas retarder le raccrochage.
                if audio_data and self._recognition_available and vm:
                    asyncio.create_task(
                        self._transcribe_voicemail_async(vm.id, audio_data),
                        name=f"stt_vm_{vm.id}",
                    )
            else:
                no_msg_reason = "vide"
                if persist_path.exists():
                    if not heard_speech:
                        logger.info(
                            "Pas de parole sur la ligne — message ignore ({})",
                            persist_path.name,
                        )
                        no_msg_reason = self.modem.last_vrx_stop_reason or "vide"
                    else:
                        logger.info("Message trop court ignore ({})", persist_path.name)
                        no_msg_reason = "trop_court"
                    try:
                        persist_path.unlink()
                    except OSError:
                        pass
                elif getattr(self.modem, "last_vrx_stop_reason", "") == "disconnect_tones":
                    no_msg_reason = "bips_raccrochage"
                    logger.info("Raccrochage pendant l'ecoute — pas de message a enregistrer")
                else:
                    no_msg_reason = self.modem.last_vrx_stop_reason or "vide"
                self._skip_incoming_recording_save = True
                self._log_call("repondeur_sans_parole", raison=no_msg_reason)
                if active_call_id:
                    try:
                        await self.call_service.mark_call_no_message(
                            active_call_id, reason=no_msg_reason
                        )
                    except Exception:
                        logger.exception(
                            "Echec marquage pas de message (appel #{})",
                            active_call_id,
                        )

            if self.modem.caller_line_finished():
                logger.info("Appelant a raccroche — fin immediate sans message de fin")
            elif getattr(self, "_skip_incoming_recording_save", False):
                self._log_call("repondeur_fin_sans_au_revoir", raison="pas_de_message")
            elif not self._call_still_active(active_call_id):
                self._log_call("repondeur_fin_sans_au_revoir", raison="appel_deja_libere")
            else:
                await self._play_on_line(
                    VOICEMAIL_GOODBYE,
                    already_in_voice_mode=self._use_modem_voice_serial(),
                    recorder=rec,
                )
        except Exception as e:
            logger.exception("Erreur mode répondeur simple: %s", e)

    async def _handle_voicemail_conversation(
        self,
        recorder: Optional[_IncomingLineRecorder] = None,
        *,
        skip_beep: bool = False,
        max_turns: int = 5,
    ) -> None:
        """
        Repondeur conversationnel : VRX continu + STT live par chunks → belief → WAV.

        Important USR5637 : un seul VRX ouvert pour le tour (pas de re-open
        par petit record). Le STT part en tache de fond sur le buffer cumule
        (port serie non touche).

        @param recorder Enregistreur parallele entrant.
        @param skip_beep True si le bip a deja ete joue apres l'accueil.
        @param max_turns Nombre max de tours dialogue.
        """
        from backend.database import database as db_module
        from backend.services import intent_repository as intent_repo
        from backend.voice.intent_belief import IntentBeliefAccumulator
        from backend.voice.node15_voice_client import Node15VoiceClient
        from backend.voice.response_picker import (
            apply_recent_tag_penalty,
            variant_wav_basename,
        )
        from backend.voice.dialogue_persona import resolve_dialogue_reply
        from backend.voice.slot_collector import start_slot_session
        from backend.voice.turn_vad import TurnVad, TurnVadConfig
        from backend.voice.audio_utils import pcm_modem_to_s16le_16k

        logger.info("Mode repondeur conversationnel (belief + intents)")
        rec = recorder or self._incoming_recorder
        active_call_id = self.current_call_id or 0
        self._log_call("conversation_debut", max_turns=max_turns, call_id=active_call_id)
        # Efface un motif VRX (ex. silence) laisse par l'appel precedent.
        try:
            self.modem.last_vrx_stop_reason = None
            self.modem.last_vrx_heard_speech = False
        except Exception:
            pass

        try:
            # Seed deja fait au demarrage API — ne pas bloquer 3-4s ici.
            db = None
            if db_module.SessionLocal is not None:
                db = db_module.SessionLocal()

            client: Optional[Node15VoiceClient] = None
            stt_url = getattr(self.config, "stt_service_url", None)
            if stt_url:
                client = Node15VoiceClient(
                    stt_url,
                    token=getattr(self.config, "stt_internal_token", None),
                    timeout_sec=45.0,
                )

            # Chunks live : silence fin de tour + periode STT (config override).
            turn_silence = float(
                getattr(self.config, "conversation_turn_silence_sec", 0.55) or 0.55
            )
            turn_silence = max(0.35, min(2.0, turn_silence))
            chunk_sec = float(
                getattr(self.config, "conversation_chunk_sec", 0.9) or 0.9
            )
            chunk_sec = max(0.6, min(2.5, chunk_sec))
            first_chunk_sec = float(
                getattr(self.config, "conversation_first_chunk_sec", 0.7) or 0.7
            )
            first_chunk_sec = max(0.5, min(chunk_sec, first_chunk_sec))
            live_stt_sec = float(
                getattr(self.config, "conversation_live_stt_sec", 3.2) or 3.2
            )
            live_stt_sec = max(2.0, min(6.0, live_stt_sec))
            # Tour court : repondre vite apres la phrase (VoIP = bruit de fond).
            max_turn_sec = int(
                getattr(self.config, "conversation_max_turn_sec", 8) or 8
            )
            max_turn_sec = max(4, min(16, max_turn_sec))
            stt_every_bytes = int(16000 * 2 * chunk_sec)
            first_stt_bytes = int(16000 * 2 * first_chunk_sec)
            # Silence raccourci quand la belief a deja un leader clair.
            early_silence_ms = max(250.0, turn_silence * 1000.0 * 0.5)
            transcript_parts: list[str] = []
            # Comme le tchat : l'ouverture salutation compte deja comme 1er tour bot.
            welcome = self._conversation_salutation_text()
            recent_replies: list[str] = [welcome]
            recent_tags: list[str] = ["salutation"]
            recent_user_texts: list[str] = []
            voice_profile = getattr(self.modem, "voice_profile", None)
            # Accueil early / ouverture deja jouee avec croche colle → pas de 2e bip tour 0.
            opening_cue_done = bool(skip_beep)

            for turn_idx in range(max_turns):
                if not self._call_still_active(active_call_id):
                    break
                if self.modem.caller_line_finished():
                    break

                belief = IntentBeliefAccumulator()
                # Seuil RMS plus haut : le fond VoIP (Yolla etc.) ne doit pas
                # resetter le chrono silence pendant 10+ s (appel #51).
                vad = TurnVad(
                    TurnVadConfig(
                        turn_silence_ms=turn_silence * 1000.0,
                        speech_rms_threshold=650.0,
                    )
                )
                committed: Optional[str] = None
                final_text = ""
                turn_pcm = bytearray()
                live_text = ""
                stt_task: Optional[asyncio.Task] = None
                last_stt_len = 0
                heard_speech = False
                speech_started_at: Optional[float] = None

                # Tour 0 apres accueil early (croche deja dans le WAV) :
                # reutilise le VRX ouvert au seize → zero trou avant parole.
                vrx_ok = False
                if (
                    turn_idx == 0
                    and opening_cue_done
                    and rec is not None
                    and getattr(rec, "_active", False)
                ):
                    try:
                        await rec.detach_reader()
                        vrx_ok = True
                        self._log_call("listen_reuse_vrx", turn=0)
                    except Exception:
                        vrx_ok = False

                if not vrx_ok:
                    if rec:
                        try:
                            await rec.pause()
                        except Exception:
                            pass
                    if not (turn_idx == 0 and opening_cue_done):
                        try:
                            await self._play_talk_cue_on_line(recorder=rec)
                        except Exception:
                            logger.warning("Talk cue tour {} ignore", turn_idx)

                self._log_call(
                    "conversation_listen",
                    turn=turn_idx,
                    chunk_s=chunk_sec,
                    first_chunk_s=first_chunk_sec,
                    silence_s=turn_silence,
                    live_stt_s=live_stt_sec,
                )
                if not vrx_ok:
                    vrx_ok = await self.modem.start_outgoing_vrx_stream(
                        already_in_voice_mode=self._use_modem_voice_serial()
                    )
                if not vrx_ok:
                    logger.warning("Conversation tour {} : VRX stream KO", turn_idx)
                    committed = "incompris"
                else:
                    deadline = time.monotonic() + float(max_turn_sec)
                    # Sans parole : coupe vite (raccrochage FR souvent = silence, pas DLE).
                    no_speech_limit = 5.0 if turn_idx == 0 else 3.0
                    no_speech_hangup_at = time.monotonic() + no_speech_limit
                    try:
                        while time.monotonic() < deadline:
                            if not self._call_still_active(active_call_id):
                                break
                            if self.modem.caller_line_finished():
                                break
                            if (
                                not heard_speech
                                and time.monotonic() >= no_speech_hangup_at
                            ):
                                logger.info(
                                    "Conversation tour {} : silence {:.1f}s sans parole — hangup",
                                    turn_idx,
                                    no_speech_limit,
                                )
                                self.modem.last_vrx_stop_reason = (
                                    self.modem.last_vrx_stop_reason or "silence_hangup"
                                )
                                break

                            # Recupere un STT live termine sans bloquer l'ecoute.
                            if stt_task is not None and stt_task.done():
                                try:
                                    result = stt_task.result()
                                    live_text = (
                                        (result.get("text") or "").strip()
                                        if isinstance(result, dict)
                                        else str(result or "").strip()
                                    )
                                except Exception as exc:
                                    logger.warning(
                                        "STT live tour {} KO: {}", turn_idx, exc
                                    )
                                    live_text = live_text or ""
                                stt_task = None
                                if live_text:
                                    await event_bus.publish(
                                        Event(
                                            event_type=EventType.CALL_TRANSCRIPTION_PARTIAL,
                                            timestamp=datetime.utcnow(),
                                            data={
                                                "call_id": active_call_id,
                                                "text": live_text,
                                                "live": True,
                                                "turn": turn_idx,
                                            },
                                            source="conversation",
                                        )
                                    )
                                    scores_map: dict[str, float] = {}
                                    try:
                                        if db is not None:
                                            preds = intent_repo.predict_intent_scores(
                                                db, live_text
                                            )
                                            scores_map = {
                                                p["tag"]: float(p["score"])
                                                for p in preds
                                                if p.get("tag")
                                            }
                                        elif client is not None:
                                            preds = await client.intent_predict(
                                                live_text
                                            )
                                            scores_map = {
                                                p["tag"]: float(p["score"])
                                                for p in preds
                                                if p.get("tag")
                                            }
                                    except Exception as exc:
                                        logger.warning(
                                            "Predict live tour {}: {}", turn_idx, exc
                                        )
                                    if scores_map and recent_tags:
                                        ranked = apply_recent_tag_penalty(
                                            [
                                                {"tag": t, "score": s}
                                                for t, s in scores_map.items()
                                            ],
                                            recent_tags,
                                        )
                                        scores_map = {
                                            p["tag"]: float(p["score"]) for p in ranked
                                        }
                                    speech_ms = max(
                                        0.0,
                                        ((len(turn_pcm) - last_stt_len) / 2) / 16.0,
                                    )
                                    if scores_map or speech_ms:
                                        belief.update(scores_map, speech_ms=speech_ms)
                                        await event_bus.publish(
                                            Event(
                                                event_type=EventType.CALL_INTENT_BELIEF,
                                                timestamp=datetime.utcnow(),
                                                data=belief.as_event_payload(
                                                    call_id=active_call_id
                                                ),
                                                source="conversation",
                                            )
                                        )
                                    committed = belief.try_commit(force=False)
                                    if committed:
                                        # "Oui" / mono-mot : ne pas couper pendant que
                                        # l'appelant enchaine (cas appel #43).
                                        words = [
                                            w
                                            for w in (live_text or "")
                                            .replace(",", " ")
                                            .split()
                                            if w
                                        ]
                                        too_short = len(words) <= 2 and len(
                                            live_text or ""
                                        ) < 20
                                        if too_short and not vad.ended:
                                            committed = None
                                        else:
                                            logger.info(
                                                "Conversation tour {} : commit precoce {}",
                                                turn_idx,
                                                committed,
                                            )
                                            break

                            raw = await self.modem.read_outgoing_vrx_chunk(2048)
                            if self.modem.caller_line_finished():
                                logger.info(
                                    "Conversation tour {} : raccrochage distant (VRX)",
                                    turn_idx,
                                )
                                break
                            if not raw:
                                await asyncio.sleep(0.01)
                                continue
                            try:
                                pcm16 = pcm_modem_to_s16le_16k(raw, voice_profile)
                            except Exception:
                                pcm16 = b""
                            if not pcm16:
                                continue
                            turn_pcm.extend(pcm16)
                            if rec:
                                try:
                                    rec.append_pcm(raw)
                                except Exception:
                                    pass
                            vad.feed_buffer(pcm16, sample_rate=16000, frame_ms=20.0)
                            if vad.heard_speech:
                                if not heard_speech:
                                    speech_started_at = time.monotonic()
                                heard_speech = True

                            # Lance un STT live sur fenetre recente (1 tache a la fois).
                            need_bytes = (
                                first_stt_bytes
                                if last_stt_len == 0
                                else stt_every_bytes
                            )
                            if (
                                heard_speech
                                and client is not None
                                and stt_task is None
                                and len(turn_pcm) - last_stt_len >= need_bytes
                            ):
                                snap = self._prepare_conversation_stt_pcm(
                                    bytes(turn_pcm), max_sec=live_stt_sec
                                )
                                last_stt_len = len(turn_pcm)

                                async def _live_stt(pcm: bytes = snap) -> dict:
                                    return await client.transcribe(pcm, mode="live")

                                stt_task = asyncio.create_task(
                                    _live_stt(), name=f"stt_live_{turn_idx}"
                                )

                            # Fin de tour : silence normal, ou plus court si belief claire.
                            if heard_speech and not committed:
                                top = belief.ranking(1)
                                leader = top[0][1] if top else 0.0
                                if vad.ended:
                                    break
                                if (
                                    leader >= 0.55
                                    and belief.state.chunks >= 1
                                    and vad.silence_ms >= early_silence_ms
                                ):
                                    logger.info(
                                        "Conversation tour {} : silence court (belief={:.2f})",
                                        turn_idx,
                                        leader,
                                    )
                                    break
                                # Cap post-parole : ne pas attendre le silence
                                # (bruit VoIP empêche silence_ms, appel #52 ~28 s).
                                if speech_started_at is not None:
                                    spoken = time.monotonic() - speech_started_at
                                    if spoken >= 4.2:
                                        logger.info(
                                            "Conversation tour {} : cap post-parole ({:.1f}s)",
                                            turn_idx,
                                            spoken,
                                        )
                                        break
                            elif vad.ended and heard_speech:
                                break
                            if len(turn_pcm) >= 16000 * 2 * max_turn_sec:
                                break
                    finally:
                        try:
                            await self.modem.end_outgoing_vrx_stream()
                        except Exception:
                            logger.exception("Fin VRX conversation tour {}", turn_idx)
                        # Drain / annule dernier STT en vol
                        if stt_task is not None:
                            if committed:
                                stt_task.cancel()
                                try:
                                    await stt_task
                                except (asyncio.CancelledError, Exception):
                                    pass
                            else:
                                # Ne pas attendre 8 s un live : STT final suit
                                # juste apres (latence appel #51).
                                try:
                                    result = await asyncio.wait_for(
                                        stt_task, timeout=1.2
                                    )
                                    live_text = (
                                        (result.get("text") or "").strip()
                                        if isinstance(result, dict)
                                        else live_text
                                    )
                                except asyncio.TimeoutError:
                                    stt_task.cancel()
                                    try:
                                        await stt_task
                                    except (asyncio.CancelledError, Exception):
                                        pass
                                except Exception:
                                    logger.warning(
                                        "STT live drain tour {} ignore", turn_idx
                                    )
                            stt_task = None

                    # Hangup possible entre ecoute et reponse (TTS / DB).
                    try:
                        await self.modem.poll_remote_hangup(max_sec=0.25)
                    except Exception:
                        pass
                    if self.modem.caller_line_finished():
                        logger.info(
                            "Conversation tour {} : raccrochage apres ecoute",
                            turn_idx,
                        )
                        break
                    if not self._call_still_active(active_call_id):
                        break

                    final_text = (live_text or "").strip()
                    # Passage final sur le tour complet : le live tronque a ~3.2s
                    # et peut s'arreter sur "Oui." alors que la phrase continue.
                    live_words = [
                        w for w in final_text.replace(",", " ").split() if w
                    ]
                    need_final = len(live_words) < 4 or len(final_text) < 24
                    if (
                        heard_speech
                        and turn_pcm
                        and client is not None
                        and need_final
                    ):
                        try:
                            snap = self._prepare_conversation_stt_pcm(
                                bytes(turn_pcm), max_sec=4.5
                            )
                            result = await asyncio.wait_for(
                                client.transcribe(snap, mode="final"),
                                timeout=5.0,
                            )
                            final_candidate = (
                                (result.get("text") or "").strip()
                                if isinstance(result, dict)
                                else ""
                            )
                            if final_candidate:
                                logger.info(
                                    "STT final tour {} : {} car. (live={} car.)",
                                    turn_idx,
                                    len(final_candidate),
                                    len(final_text),
                                )
                                final_text = final_candidate
                        except asyncio.TimeoutError:
                            logger.warning(
                                "STT final tour {} timeout — on garde live",
                                turn_idx,
                            )
                        except Exception:
                            logger.exception("STT final tour {} ignore", turn_idx)
                    elif heard_speech and final_text and not need_final:
                        logger.info(
                            "STT final tour {} saute (live deja complet: {} car.)",
                            turn_idx,
                            len(final_text),
                        )
                    if heard_speech and not final_text and turn_pcm:
                        # Repli rapide (pas de jingle long : appel #53 ~35 s muets).
                        try:
                            if client is not None:
                                snap = self._prepare_conversation_stt_pcm(
                                    bytes(turn_pcm), max_sec=4.0
                                )
                                result = await asyncio.wait_for(
                                    client.transcribe(snap, mode="live"),
                                    timeout=4.0,
                                )
                                final_text = (
                                    (result.get("text") or "").strip()
                                    if isinstance(result, dict)
                                    else ""
                                )
                                logger.info(
                                    "STT repli live tour {} : {} car.",
                                    turn_idx,
                                    len(final_text),
                                )
                        except Exception:
                            logger.exception("STT repli tour {}", turn_idx)
                            final_text = ""
                    if heard_speech and final_text:
                        # Predict final sur le texte complet (pas le live tronque).
                        scores_map = {}
                        try:
                            if db is not None:
                                preds = intent_repo.predict_intent_scores(db, final_text)
                                ranked = [
                                    {"tag": p["tag"], "score": float(p["score"])}
                                    for p in preds
                                    if p.get("tag")
                                ]
                                # Boost lexical persona (contacter / Daniel / etc.)
                                # avant le commit force — sinon incompris sous 0.35.
                                from backend.voice.dialogue_persona import (
                                    reshape_predictions,
                                )

                                ranked = reshape_predictions(
                                    ranked,
                                    recent_tags=recent_tags,
                                    user_text=final_text,
                                )
                                if recent_tags:
                                    ranked = apply_recent_tag_penalty(
                                        ranked, recent_tags
                                    )
                                scores_map = {
                                    p["tag"]: float(p["score"]) for p in ranked
                                }
                        except Exception as exc:
                            logger.warning("Predict final tour {}: {}", turn_idx, exc)
                        if scores_map:
                            belief.update(scores_map, speech_ms=200.0)
                            # Recalcule le commit avec le texte complet.
                            committed = belief.try_commit(force=True) or committed

                    if not heard_speech or not turn_pcm:
                        logger.info(
                            "Conversation tour {} : silence sans parole — fin d'appel",
                            turn_idx,
                        )
                        self.modem.last_vrx_stop_reason = (
                            self.modem.last_vrx_stop_reason or "silence_hangup"
                        )
                        break
                    else:
                        if final_text:
                            transcript_parts.append(final_text)
                            await event_bus.publish(
                                Event(
                                    event_type=EventType.CALL_TRANSCRIPTION_PARTIAL,
                                    timestamp=datetime.utcnow(),
                                    data={
                                        "call_id": active_call_id,
                                        "text": final_text,
                                        "live": False,
                                        "turn": turn_idx,
                                    },
                                    source="conversation",
                                )
                            )
                        if not committed:
                            committed = belief.try_commit(force=True) or "incompris"

                if not committed:
                    committed = "incompris"

                action = None
                response_text = None
                response_index = 0
                wav_basename = f"kb_{committed}"
                if db is not None and committed:
                    # Predictions belief → liste pour persona
                    preds_list = [
                        {"tag": t, "score": float(s)} for t, s in belief.ranking(8)
                    ]
                    if not preds_list and committed:
                        preds_list = [{"tag": committed, "score": 1.0}]

                    # Prefere le top reshaped pour le catalogue (pas incompris
                    # si la persona va jouer contacter_personne).
                    from backend.voice.dialogue_persona import reshape_predictions

                    reshaped_preview = reshape_predictions(
                        preds_list,
                        recent_tags=recent_tags,
                        user_text=final_text or "",
                    )
                    catalog_tag = (
                        str(reshaped_preview[0]["tag"])
                        if reshaped_preview
                        else committed
                    )
                    intent = intent_repo.get_intent_by_tag(db, catalog_tag)
                    if intent is None:
                        intent = intent_repo.get_intent_by_tag(db, committed)
                    catalog = []
                    if intent is not None:
                        action = intent.action
                        wav_basename = intent.wav_basename or f"kb_{intent.tag}"
                        catalog = [
                            r.text
                            for r in sorted(intent.responses, key=lambda r: r.position)
                        ]

                    user_utt = final_text or ""
                    resolved = resolve_dialogue_reply(
                        user_text=user_utt,
                        predictions=preds_list,
                        recent_tags=recent_tags,
                        recent_replies=recent_replies,
                        recent_user_texts=recent_user_texts,
                        catalog_responses=catalog,
                    )
                    response_text = str(resolved.get("reply") or "") or None
                    response_index = int(
                        resolved.get("response_index")
                        if resolved.get("response_index") is not None
                        else -1
                    )
                    resolved_tag = str(resolved.get("tag") or committed)
                    # Aligne commit DB / action sur le tag vraiment joue.
                    if resolved_tag and resolved_tag != committed and resolved_tag != "insulte":
                        committed = resolved_tag
                        intent2 = intent_repo.get_intent_by_tag(db, committed)
                        if intent2 is not None:
                            intent = intent2
                            if not resolved.get("action"):
                                action = intent2.action
                    if resolved.get("action"):
                        action = resolved.get("action")
                    if response_index >= 0 and resolved_tag:
                        wav_basename = variant_wav_basename(
                            str(resolved_tag), response_index
                        )
                        if (
                            response_index == 0
                            and intent is not None
                            and intent.wav_basename
                            and str(resolved_tag) == intent.tag
                        ):
                            wav_basename = intent.wav_basename

                    if user_utt:
                        recent_user_texts.append(user_utt)
                        if len(recent_user_texts) > 12:
                            recent_user_texts = recent_user_texts[-12:]

                await event_bus.publish(
                    Event(
                        event_type=EventType.CALL_INTENT_COMMIT,
                        timestamp=datetime.utcnow(),
                        data={
                            "call_id": active_call_id,
                            "tag": committed,
                            "turn": turn_idx,
                            "text": final_text,
                            "belief": belief.as_event_payload(call_id=active_call_id),
                        },
                        source="conversation",
                    )
                )
                self._log_call("conversation_commit", tag=committed, turn=turn_idx)

                if active_call_id and committed:
                    try:
                        joined = (
                            " | ".join(transcript_parts) if transcript_parts else None
                        )
                        cues = None
                        if joined:
                            from backend.voice.transcript_cues import (
                                build_transcript_cues,
                                offset_transcript_cues,
                            )

                            offset_sec = 0.0
                            if rec is not None:
                                try:
                                    offset_sec = float(rec.seed_duration_sec())
                                except Exception:
                                    offset_sec = 0.0
                            speech_dur = max(2.0, len(joined.split()) * 0.38)
                            cues = build_transcript_cues(
                                joined, duration_sec=speech_dur
                            )
                            if offset_sec > 0.05:
                                cues = offset_transcript_cues(cues, offset_sec)
                                logger.info(
                                    "Cues SRT decales de {:.2f}s (accueil seed)",
                                    offset_sec,
                                )
                        await self.call_service.set_transcription_and_intent(
                            int(active_call_id),
                            transcription=joined,
                            intent_name=committed,
                            cues=cues,
                        )
                    except Exception:
                        logger.exception("Maj intent appel #{}", active_call_id)

                if response_text:
                    recent_replies.append(response_text)
                    if len(recent_replies) > 12:
                        recent_replies = recent_replies[-12:]
                if committed:
                    recent_tags.append(committed)
                    if len(recent_tags) > 12:
                        recent_tags = recent_tags[-12:]

                try:
                    await self.modem.poll_remote_hangup(max_sec=0.15)
                except Exception:
                    pass
                if (
                    not self._call_still_active(active_call_id)
                    or self.modem.caller_line_finished()
                ):
                    logger.info(
                        "Conversation tour {} : raccrochage avant reponse",
                        turn_idx,
                    )
                    break

                played = await self._play_intent_wav_or_tts(
                    wav_basename=wav_basename,
                    response_text=response_text or "D'accord.",
                    recorder=rec,
                )
                if not played:
                    if self.modem.caller_line_finished() or getattr(
                        self.modem, "_playback_interrupted", False
                    ):
                        logger.info(
                            "Conversation tour {} : raccrochage pendant reponse ({})",
                            turn_idx,
                            committed,
                        )
                    else:
                        logger.warning(
                            "Lecture reponse intent {} echouee — on arrete (modem voix KO?)",
                            committed,
                        )
                    break

                if committed == "fin" or action == "hangup_soft":
                    break
                if action in ("record_message",) or committed in (
                    "absent_laisser_message",
                    "urgence",
                    "rappel_callback",
                    "parler_humain",
                ):
                    await self._handle_voicemail_simple(recorder=rec, skip_beep=False)
                    break

                # Collecte multi-tours (coords / email / creneau RDV)
                slot_session = start_slot_session(action, committed or "")
                if slot_session is not None:
                    await self._collect_slots_conversation(
                        slot_session,
                        db=db,
                        client=client,
                        recorder=rec,
                        call_id=active_call_id,
                        turn_silence=turn_silence,
                        chunk_sec=float(max_turn_sec),
                    )
                    # Apres collecte, on peut encher un autre tour ou finir
                    if self.modem.caller_line_finished():
                        break

                if self.modem.caller_line_finished():
                    break

            if db is not None:
                db.close()

            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass

            if (
                self._call_still_active(active_call_id)
                and not self.modem.caller_line_finished()
            ):
                # Goodbye deja joue si intent fin ; sinon court au revoir
                pass
        except Exception as e:
            logger.exception("Erreur mode repondeur conversation: {}", e)

    async def _collect_slots_conversation(
        self,
        slot_session,
        *,
        db,
        client,
        recorder,
        call_id: int,
        turn_silence: float,
        chunk_sec: float,
        max_retries_per_slot: int = 2,
    ) -> None:
        """
        Dialogue multi-tours pour remplir nom / tel / email / creneau.

        @param slot_session Session de slots active.
        @param db Session SQLAlchemy (peut etre None).
        @param client Client node15 optionnel.
        @param recorder Enregistreur ligne.
        @param call_id ID appel.
        @param turn_silence Silence fin de tour (s).
        @param chunk_sec Duree max chunk (s).
        @param max_retries_per_slot Tentatives par slot.
        """
        from backend.voice.slot_collector import confirmation_text, feed_slot_utterance, persist_call_lead

        while not slot_session.done:
            if not self._call_still_active(call_id) or self.modem.caller_line_finished():
                break
            prompt = slot_session.current_prompt()
            await self._play_on_line(
                prompt,
                already_in_voice_mode=self._use_modem_voice_serial(),
                recorder=recorder,
            )
            filled = False
            for _attempt in range(max_retries_per_slot):
                if not self._call_still_active(call_id) or self.modem.caller_line_finished():
                    break
                pcm = await self._record_audio(
                    duration=max(4, int(round(chunk_sec))),
                    already_in_voice_mode=self._use_modem_voice_serial(),
                    recorder=recorder,
                    stop_on_remote_hangup=True,
                    silence_timeout_sec=max(1.2, turn_silence),
                )
                if not pcm:
                    continue
                text = ""
                try:
                    if client is not None:
                        text = (await client.transcribe(pcm, mode="final")).get("text") or ""
                    elif self._recognition_available:
                        text, _ = await self.voice_recognition.transcribe_with_cues(
                            pcm, sample_rate=16000
                        )
                except Exception as exc:
                    logger.warning("STT slot: {}", exc)
                text = (text or "").strip()
                if text:
                    await event_bus.publish(
                        Event(
                            event_type=EventType.CALL_TRANSCRIPTION_PARTIAL,
                            timestamp=datetime.utcnow(),
                            data={
                                "call_id": call_id,
                                "text": text,
                                "live": True,
                                "slot": slot_session.pending_slots[0]
                                if slot_session.pending_slots
                                else None,
                            },
                            source="conversation_slots",
                        )
                    )
                if feed_slot_utterance(slot_session, text):
                    filled = True
                    break
                await self._play_on_line(
                    "Je n'ai pas bien compris. Pouvez-vous repeter ?",
                    already_in_voice_mode=self._use_modem_voice_serial(),
                    recorder=recorder,
                )
            if not filled:
                # Skip ce slot pour ne pas bloquer l'appel
                if slot_session.pending_slots:
                    slot_session.pending_slots.pop(0)

        if db is not None and slot_session.values:
            phone = None
            try:
                call_row = self.call_service.call_repo.get_by_id(call_id)
                if call_row:
                    phone = call_row.phone_number
            except Exception:
                pass
            try:
                persist_call_lead(
                    db,
                    slot_session,
                    call_id=call_id or None,
                    phone_number=phone,
                )
            except Exception:
                logger.exception("Echec persist call_lead")
            await self._play_on_line(
                confirmation_text(slot_session),
                already_in_voice_mode=self._use_modem_voice_serial(),
                recorder=recorder,
            )

    async def _play_intent_wav_or_tts(
        self,
        *,
        wav_basename: str,
        response_text: str,
        recorder: Optional[_IncomingLineRecorder] = None,
    ) -> bool:
        """
        Joue le WAV cache kb_* s'il correspond au texte, sinon regenerate / TTS.

        @param wav_basename Nom sans extension sous ivr_wav/.
        @param response_text Texte cible (variante anti-repetition).
        @param recorder Enregistreur a mettre en pause.
        @returns True si lecture OK.
        """
        if not self._call_still_active(self.current_call_id) or self.modem.caller_line_finished():
            return False
        try:
            await self.modem.poll_remote_hangup(max_sec=0.1)
        except Exception:
            pass
        if self.modem.caller_line_finished():
            return False
        base = Path(self.config.base_path) if self.config.base_path else Path.cwd()
        wav_path = base / "ivr_wav" / f"{wav_basename}.wav"
        # Si le WAV existe mais ne matche pas le texte choisi → rebuild via cache
        try:
            if wav_path.is_file() and self._ivr_cache.is_fresh(wav_basename, response_text):
                return await self._play_wav_file_on_line(
                    wav_path,
                    already_in_voice_mode=self._use_modem_voice_serial(),
                    recorder=recorder,
                )
        except Exception:
            logger.debug("Check fraicheur WAV intent ignore")

        try:
            path = await self._ivr_cache.ensure(response_text, wav_basename)
            if path and path.is_file():
                return await self._play_wav_file_on_line(
                    path,
                    already_in_voice_mode=self._use_modem_voice_serial(),
                    recorder=recorder,
                )
        except Exception:
            logger.exception("Cache IVR intent echoue")
        return await self._play_on_line(
            response_text,
            already_in_voice_mode=self._use_modem_voice_serial(),
            recorder=recorder,
        )

    async def _transcribe_voicemail_async(self, voicemail_id: int, audio_pcm_16k: bytes) -> None:
        """
        Transcrit un message vocal (STT) sans bloquer la ligne telephonique.

        Met a jour la VM et, si lie, la transcription de l'appel pour l'UI /calls.

        @param voicemail_id ID du message en base.
        @param audio_pcm_16k PCM 16 kHz 16-bit mono (sortie de ``_record_audio``).
        """
        try:
            text, cues = await self.voice_recognition.transcribe_with_cues(
                audio_pcm_16k, sample_rate=16000
            )
            text = (text or "").strip()
            if not text:
                logger.info("STT message #{} : vide / inaudible", voicemail_id)
                return
            vm = await self.call_service.set_voicemail_transcription(voicemail_id, text)
            call_id = getattr(vm, "call_id", None) if vm is not None else None
            if call_id:
                try:
                    await self.call_service.set_transcription_and_intent(
                        int(call_id), transcription=text, cues=cues or None
                    )
                except Exception:
                    logger.exception(
                        "STT message #{} : echec maj transcription appel #{}",
                        voicemail_id,
                        call_id,
                    )
            logger.info("STT message #{} : {}", voicemail_id, text[:120])
        except Exception:
            logger.exception("STT message #{} echoue", voicemail_id)

    async def _play_beep_on_line(self, recorder: Optional[_IncomingLineRecorder] = None) -> bool:
        """
        Joue un bip court sur la ligne (WAV configure ou genere).

        @param recorder Enregistreur entrant a mettre en pause pendant le bip.
        @returns True si la lecture a reussi.
        """
        if not self.modem.is_initialized:
            return False
        audio = self._audio_settings()
        if audio.record_beep == "none":
            return True
        if audio.record_beep == "dtmf":
            if await self.modem.send_dtmf("1"):
                return True
            logger.warning("Bip DTMF echoue (USR) — repli WAV")
        configured = beep_wav_path(self.config, audio)
        beep_path = configured or (self._ensure_ivr_wav_dir() / "voicemail_beep.wav")
        if not beep_path.is_file():
            write_beep_wav_8k(beep_path, profile=getattr(self.modem, "voice_profile", None))
        if self._use_modem_voice_serial() and not getattr(self.modem, "_voice_line_ready", False):
            await self.modem.prepare_voice_line_after_seize()
        return await self._play_wav_file_on_line(
            beep_path,
            already_in_voice_mode=True,
            recorder=recorder,
        )

    def _ensure_talk_cue_wav(self) -> Path:
        """
        Croche legere a deux notes (signal « a vous de parler »).

        Regen si absent, trop court, ou format incompatible avec le profil modem
        (ex. fichier 11 kHz alors que le daemon tourne en 8 kHz u8).

        @returns Chemin ivr_wav/talk_cue.wav.
        """
        path = self._ensure_ivr_wav_dir() / "talk_cue.wav"
        profile = getattr(self.modem, "voice_profile", None)
        need = (
            (not path.is_file())
            or path.stat().st_size < 800
            or not wav_matches_modem_profile(path, profile=profile)
        )
        if need:
            write_talk_cue_wav_8k(path, profile=profile)
        return path

    def _append_talk_cue_to_wav(self, wav_path: Path, *, gap_ms: int = 220) -> None:
        """
        Colle la croche « a vous » a la fin d'un WAV (accueil early).

        Evite le trou de plusieurs secondes entre l'annonce et le bip si le
        bip etait joue apres le setup DB/STT.

        @param wav_path Fichier a enrichir sur place.
        @param gap_ms Silence court avant la croche.
        """
        if not wav_path.is_file() or wav_path.stat().st_size < 1000:
            return
        profile = getattr(self.modem, "voice_profile", None)
        marker = wav_path.with_suffix(wav_path.suffix + ".talkcue")
        cue = self._ensure_talk_cue_wav()
        # Si l'accueil n'est plus au bon format (ex. 11 kHz vs 8 kHz), repartir
        # de la voix nue avant de recoller la croche.
        bare = wav_path.with_name(wav_path.stem + "_voice.wav")
        if bare.is_file() and not wav_matches_modem_profile(wav_path, profile=profile):
            try:
                import shutil

                shutil.copy2(bare, wav_path)
                if marker.is_file():
                    marker.unlink()
            except OSError as exc:
                logger.warning("Restore {} depuis voix nue echoue: {}", wav_path.name, exc)
        # Evite de coller deux fois la croche a chaque warmup.
        if (
            marker.is_file()
            and marker.stat().st_mtime >= wav_path.stat().st_mtime
            and marker.stat().st_mtime >= cue.stat().st_mtime
            and wav_matches_modem_profile(wav_path, profile=profile)
        ):
            return
        # Si deja colle avec une ancienne croche, restaurer la voix nue.
        if bare.is_file() and marker.is_file():
            try:
                import shutil

                shutil.copy2(bare, wav_path)
            except OSError:
                pass
        try:
            combine_modem_wav_files(
                [wav_path, cue],
                wav_path,
                gap_ms=max(80, int(gap_ms)),
                normalize=False,
                profile=profile,
            )
            marker.write_text("ok\n", encoding="utf-8")
            logger.info(
                "Talk cue colle sur {} (gap={} ms)",
                wav_path.name,
                gap_ms,
            )
        except Exception as exc:
            logger.warning("Append talk cue sur {} echoue: {}", wav_path.name, exc)

    async def _play_talk_cue_on_line(
        self, recorder: Optional[_IncomingLineRecorder] = None
    ) -> bool:
        """
        Joue la croche « a vous » apres l'accueil conversation.

        @param recorder Enregistreur a pauser pendant la lecture.
        @returns True si lecture OK.
        """
        if not self.modem.is_initialized:
            return False
        cue = self._ensure_talk_cue_wav()
        self._log_call("talk_cue", fichier=cue.name)
        if self._use_modem_voice_serial() and not getattr(self.modem, "_voice_line_ready", False):
            await self.modem.prepare_voice_line_after_seize()
        return await self._play_wav_file_on_line(
            cue,
            already_in_voice_mode=True,
            recorder=recorder,
        )

    async def _handle_voice_interaction(self, recorder: Optional[_IncomingLineRecorder] = None):
        """Gère l'interaction vocale avec l'appelant"""
        logger.info("Démarrage de l'interaction vocale")

        if not self._voice_available:
            await self._play_on_line(
                "Veuillez laisser votre message après le bip.",
                already_in_voice_mode=self._use_modem_voice_serial(),
                recorder=recorder,
            )
            await self._record_message(recorder=recorder)
            return

        try:
            # Enregistrer l'audio depuis la ligne (après le message d'accueil joué sur la ligne)
            audio_data = await self._record_audio(
                duration=self.config.voicemail_max_duration,
                already_in_voice_mode=self._use_modem_voice_serial(),
                recorder=recorder,
                stop_on_remote_hangup=True,
                silence_timeout_sec=float(getattr(self.config, "voicemail_silence_timeout_sec", 3) or 3),
            )
            
            if not audio_data:
                logger.warning("Aucun audio enregistré")
                return
            
            # Publier l'événement de début de reconnaissance
            await event_bus.publish(Event(
                event_type=EventType.VOICE_RECOGNITION_STARTED,
                timestamp=datetime.utcnow(),
                data={"call_id": self.current_call_id},
                source="CallManager"
            ))
            
            # Transcrire la parole (audio en 16 kHz 16-bit)
            transcription = await self.voice_recognition.transcribe(audio_data, sample_rate=16000)
            logger.info(f"Transcription: {transcription}")
            
            # Publier l'événement de fin de reconnaissance
            await event_bus.publish(Event(
                event_type=EventType.VOICE_RECOGNITION_COMPLETED,
                timestamp=datetime.utcnow(),
                data={
                    "call_id": self.current_call_id,
                    "transcription": transcription
                },
                source="CallManager"
            ))
            
            # Traiter la commande vocale (IVR patterns puis LLM)
            response = await self._process_voice_command(transcription)
            
            # Répondre sur la ligne (WAV 8 kHz vers le modem ou ALSA)
            if response:
                await self._play_on_line(response, already_in_voice_mode=self._use_modem_voice_serial(), recorder=recorder)

        except Exception as e:
            logger.exception(f"Erreur lors de l'interaction vocale: {e}")
            await self._play_on_line(
                "Désolé, je n'ai pas compris. Veuillez laisser un message après le bip.",
                already_in_voice_mode=self._use_modem_voice_serial(),
                recorder=recorder,
            )
            await self._record_message(recorder=recorder)
    
    async def _process_voice_command(self, transcription: str) -> Optional[str]:
        """
        Traite une commande vocale via patterns metier
        
        Args:
            transcription: Texte transcrit
            
        Returns:
            Réponse vocale ou None
        """
        if not transcription:
            return None
        
        transcription_lower = transcription.lower()
        
        # Commandes spéciales (prioritaires)
        if "message" in transcription_lower or "laisser" in transcription_lower:
            await self._record_message()
            return "Très bien, vous pouvez laisser votre message maintenant."
        
        if "raccrocher" in transcription_lower or "au revoir" in transcription_lower:
            return "Au revoir, bonne journée!"

        # 1) Essayer le moteur d'intents IVR (patterns) en priorité
        try:
            intent = self.ivr_engine.match_intent(transcription)
            response_text, _ = self.ivr_engine.get_response_and_filename(intent)
            if response_text:
                # Sauvegarder transcription + intent sur l'appel courant
                if self.current_call_id:
                    try:
                        await self.call_service.set_transcription_and_intent(
                            self.current_call_id,
                            transcription=transcription,
                            intent_name=intent.get("name"),
                        )
                    except Exception as e:
                        logger.warning("Impossible de mettre a jour l'appel avec l'intent IVR: {}", e)
                auto_appointment = None
                try:
                    caller_phone_number = None
                    if self.current_call_id:
                        call_row = self.db.query(Call).filter(Call.id == self.current_call_id).first()
                        if call_row:
                            caller_phone_number = call_row.phone_number
                    auto_appointment = self.appointment_service.maybe_schedule_from_intent(
                        intent_name=intent.get("name"),
                        transcription=transcription,
                        call_id=self.current_call_id,
                        phone_number=caller_phone_number,
                    )
                except Exception as e:
                    logger.warning("Creation auto du rendez-vous impossible: {}", e)

                if auto_appointment:
                    start_label = auto_appointment.start_time.strftime("%d/%m a %H:%M")
                    return f"{response_text} Je vous propose le {start_label}. Vous pourrez le modifier depuis l agenda."
                return response_text
        except Exception as e:
            logger.warning(f"Erreur dans le moteur IVR patterns: {e}")
        
        # 2) Sinon, deleguer la generation de reponse au service de conversation
        try:
            reply = await self.conversation_service.generate_reply(transcription)
            if reply:
                return reply
        except Exception as e:
            logger.warning(f"Erreur dans le service de conversation, fallback vers reponse par defaut: {e}")
        
        # 3) Fallback: réponse par défaut
        return "Je n'ai pas bien compris. Voulez-vous laisser un message?"
    
    async def _play_wav_file_on_line(
        self,
        wav_path: Path,
        *,
        already_in_voice_mode: bool = False,
        recorder: Optional[_IncomingLineRecorder] = None,
    ) -> bool:
        """
        Joue un fichier WAV 8 kHz sur la ligne.

        @param wav_path Fichier WAV.
        @param already_in_voice_mode Deja en mode voix modem.
        @param recorder Enregistreur a pauser.
        @returns True si lecture OK.
        """
        if not self.modem.is_initialized or not wav_path.is_file():
            return False
        self._log_call("play_wav", fichier=wav_path.name)
        rec = recorder or self._incoming_recorder
        if rec:
            await rec.pause()
        try:
            if self._use_modem_voice_serial():
                ok = await self.modem.play_wav_via_serial(
                    wav_path, already_in_voice_mode=already_in_voice_mode
                )
                self._log_call("play_wav_fin", fichier=wav_path.name, ok=int(ok))
                return ok
            proc = await asyncio.create_subprocess_exec(
                "aplay",
                "-D",
                self._alsa_play,
                "-q",
                str(wav_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        finally:
            if rec:
                await rec.resume(already_in_voice_mode=True)

    def _track_greeting_voice_key(self, audio) -> tuple[str, str, str]:
        """
        Cle voix TTS pour invalider le cache track si Vivienne/pitch change.

        @param audio Bloc IncomingCallAudioConfig.
        @returns Tuple (voix, pitch, rate).
        """
        return (
            str(getattr(audio, "edge_tts_voice", "") or ""),
            str(getattr(audio, "edge_tts_pitch", "") or ""),
            str(getattr(audio, "edge_tts_rate", "") or ""),
        )

    def _track_greeting_cache_path(
        self,
        intro: Path,
        audio,
        greeting: str,
    ) -> Path:
        """
        Chemin cache du mix piste + voix (meme cle que le warmup).

        @param intro Piste musicale.
        @param audio Config audio.
        @param greeting Texte accueil.
        @returns Fichier WAV cache sous ivr_wav/.
        """
        intro_ms = int(float(getattr(audio, "greeting_intro_sec", 2.0) or 2.0) * 1000)
        crossfade_ms = int(float(getattr(audio, "greeting_intro_crossfade_ms", 450) or 450))
        music_offset_ms = int(
            float(getattr(audio, "greeting_intro_music_offset_sec", 0.0) or 0.0) * 1000
        )
        track_duck_db = float(getattr(audio, "greeting_intro_track_duck_db", 0.0) or 0.0)
        voice_gain = float(getattr(audio, "greeting_intro_voice_gain_db", 0.0) or 0.0)
        voice_key = self._track_greeting_voice_key(audio)
        intro_key = str(intro.resolve())
        return self._ensure_ivr_wav_dir() / (
            "greeting_track_"
            f"{hash((intro_key, intro_ms, crossfade_ms, music_offset_ms, track_duck_db, voice_gain, greeting, voice_key)) % 2**31}.wav"
        )

    def _track_greeting_cache_stale(self, combined: Path, intro: Path, voice_wav: Path) -> bool:
        """
        True si le cache track doit etre regenere.

        @param combined Fichier mix cache.
        @param intro Piste source.
        @param voice_wav Voix TTS modem.
        @returns True si absent ou plus vieux qu'une source.
        """
        if not combined.is_file() or combined.stat().st_size < 2000:
            return True
        cache_mtime = combined.stat().st_mtime
        for dep in (intro, voice_wav):
            try:
                if dep.is_file() and dep.stat().st_mtime > cache_mtime:
                    return True
            except OSError:
                return True
        return False

    async def _ensure_track_greeting_wav(
        self,
        intro: Path,
        voice_wav: Path,
        audio,
        greeting: str,
    ) -> Path:
        """
        Retourne le WAV mix piste+voix, pre-genere au demarrage ou en tache de fond.

        @param intro Piste musicale.
        @param voice_wav Message vocal modem.
        @param audio Config audio.
        @param greeting Texte accueil.
        @returns Chemin WAV pret pour le modem.
        """
        combined = self._track_greeting_cache_path(intro, audio, greeting)
        if not self._track_greeting_cache_stale(combined, intro, voice_wav):
            logger.info("Accueil track cache: {}", combined.name)
            return combined
        intro_ms = int(float(getattr(audio, "greeting_intro_sec", 2.0) or 2.0) * 1000)
        crossfade_ms = int(float(getattr(audio, "greeting_intro_crossfade_ms", 450) or 450))
        music_offset_ms = int(
            float(getattr(audio, "greeting_intro_music_offset_sec", 0.0) or 0.0) * 1000
        )
        track_duck_db = float(getattr(audio, "greeting_intro_track_duck_db", 0.0) or 0.0)
        voice_gain = float(getattr(audio, "greeting_intro_voice_gain_db", 0.0) or 0.0)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: combine_music_track_voice_overlay(
                intro,
                voice_wav,
                combined,
                music_solo_ms=intro_ms,
                music_offset_ms=music_offset_ms,
                voice_fade_ms=crossfade_ms,
                music_duck_db=track_duck_db if track_duck_db > 0.5 else None,
                voice_mix_gain_db=voice_gain,
            ),
        )
        logger.info("Accueil track regenere: {}", combined.name)
        return combined

    async def _play_greeting_sequence(
        self,
        *,
        greeting: str,
        audio,
        already_in_voice_mode: bool = False,
        recorder: Optional[_IncomingLineRecorder] = None,
    ) -> bool:
        """
        Joue l'intro musicale puis le message d'accueil en une seule session VTX (fluide).

        @param greeting Texte d'accueil effectif.
        @param audio Bloc IncomingCallAudioConfig.
        @param already_in_voice_mode Deja en mode voix modem.
        @param recorder Enregistreur parallele.
        @returns True si au moins la voix d'accueil a ete jouee.
        """
        self._log_call("accueil_debut", mode="sequence")
        if self._use_modem_voice_serial() and already_in_voice_mode:
            if not getattr(self.modem, "_voice_line_ready", False):
                await self.modem.prepare_voice_line_after_seize()

        cached_active = self._resolve_early_greeting_wav_path()
        if cached_active and cached_active.is_file():
            logger.info("Accueil cache modem: {}", cached_active.name)
            ok = await self._play_wav_file_on_line(
                cached_active,
                already_in_voice_mode=already_in_voice_mode,
                recorder=recorder,
            )
            self._log_call("accueil_fin", source="cache", ok=int(ok))
            return ok

        intro = greeting_intro_path(self.config, audio)
        greeting_wav = await self._resolve_greeting_modem_wav(greeting, audio)
        intro_mode = str(getattr(audio, "greeting_intro_mode", "none") or "none")
        if intro and intro.is_file() and greeting_wav and greeting_wav.is_file():
            intro_ms = int(float(getattr(audio, "greeting_intro_sec", 3.2) or 3.2) * 1000)
            crossfade_ms = int(float(getattr(audio, "greeting_intro_crossfade_ms", 520) or 520))
            intro_variant = str(getattr(audio, "greeting_intro_variant", "tesla") or "tesla")
            bed_db = resolve_intro_voice_bed_gain_db(audio, intro_variant)
            voice_gain = float(getattr(audio, "greeting_intro_voice_gain_db", 0.0) or 0.0)
            from backend.voice.musicscreen_jingles import is_musicscreen_jingle

            bed_variant = getattr(audio, "greeting_intro_bed_variant", None)
            if bed_variant is None and not is_musicscreen_jingle(intro_variant):
                bed_variant = default_bed_variant_for_jingle(intro_variant)
            if intro_mode == "track":
                try:
                    combined = await self._ensure_track_greeting_wav(
                        intro,
                        greeting_wav,
                        audio,
                        greeting,
                    )
                    logger.info("Accueil combine (piste): musique + voix -> {}", combined.name)
                    ok = await self._play_wav_file_on_line(
                        combined,
                        already_in_voice_mode=already_in_voice_mode,
                        recorder=recorder,
                    )
                    self._log_call("accueil_fin", source="track", ok=int(ok))
                    return ok
                except Exception as exc:
                    logger.warning("Accueil piste echoue ({}), lecture en deux temps", exc)
            else:
                combined = self._ensure_ivr_wav_dir() / f"greeting_seq_{hash((str(intro), intro_ms, crossfade_ms, bed_db, voice_gain, intro_variant, bed_variant, greeting)) % 2**31}.wav"
                try:
                    combine_intro_voice_crossfade(
                        intro,
                        greeting_wav,
                        combined,
                        crossfade_ms=crossfade_ms,
                        intro_max_ms=intro_ms,
                        intro_variant=intro_variant,
                        normalize=True,
                        voice_bed_gain_db=bed_db,
                        voice_mix_gain_db=voice_gain,
                        voice_bed_variant=str(bed_variant),
                    )
                    logger.info("Accueil combine (fondu): intro + voix -> {}", combined.name)
                    ok = await self._play_wav_file_on_line(
                        combined,
                        already_in_voice_mode=already_in_voice_mode,
                        recorder=recorder,
                    )
                    self._log_call("accueil_fin", source="crossfade", ok=int(ok))
                    return ok
                except Exception as exc:
                    logger.warning("Accueil combine echoue ({}), lecture en deux temps", exc)

        if intro and intro.is_file():
            logger.info("Intro accueil: {}", intro.name)
            intro_ok = await self._play_wav_file_on_line(
                intro,
                already_in_voice_mode=already_in_voice_mode,
                recorder=recorder,
            )
            if not intro_ok:
                logger.warning("Intro musicale echouee — poursuite vers message vocal")
            elif getattr(self.modem, "_playback_interrupted", False):
                self._log_call("accueil_fin", source="intro_interrompu", ok=0)
                return False
            already_in_voice_mode = True

        ok = await self._play_configured_message(
            source=audio.greeting_source,
            wav_path=audio.greeting_wav_path,
            tts_text=greeting,
            fallback_text=greeting,
            already_in_voice_mode=already_in_voice_mode,
            recorder=recorder,
        )
        self._log_call("accueil_fin", source="message", ok=int(ok))
        return ok

    async def _resolve_greeting_modem_wav(self, greeting: str, audio) -> Optional[Path]:
        """
        Retourne le WAV 8 kHz du message d'accueil (cache IVR ou generation TTS).

        @param greeting Texte d'accueil effectif.
        @param audio Bloc audio incoming_call.
        @returns Chemin WAV modem ou None.
        """
        if audio.greeting_source == "wav":
            resolved = pick_wav_or_none(self.config, audio, source="wav", wav_path=audio.greeting_wav_path)
            if resolved:
                return resolved
        text = (greeting or "").strip()
        if not text or not self._voice_available:
            return None
        basename = self._ivr_basename_for_text(text)
        if basename:
            cached = self._ivr_cache.get_if_fresh(text, basename)
            if cached:
                return cached
        try:
            from pydub import AudioSegment
        except ImportError:
            return None
        temp_tts = await self.voice_synthesis.speak(
            text,
            rate=getattr(self.config, "edge_tts_rate", "+0%"),
            pitch=getattr(self.config, "edge_tts_pitch", "+0Hz"),
        )
        if not temp_tts or not Path(temp_tts).exists():
            return None
        ivr_dir = self._ensure_ivr_wav_dir()
        out_wav = ivr_dir / f"ivr_live_{hash(text) % 2**31}.wav"
        try:
            tts_source_to_modem_wav(
                Path(temp_tts),
                out_wav,
                voice_gain_db=float(getattr(self.config, "edge_tts_voice_gain_db", -6.0) or -6.0),
            )
            return out_wav
        except Exception as exc:
            logger.warning("resolve_greeting_modem_wav: {}", exc)
            return None

    async def _play_configured_message(
        self,
        *,
        source: str,
        wav_path: Optional[str],
        tts_text: Optional[str],
        fallback_text: str,
        already_in_voice_mode: bool = False,
        recorder: Optional[_IncomingLineRecorder] = None,
    ) -> bool:
        """
        Joue un message configure (WAV statique ou TTS).

        @param source ``wav`` ou ``tts``.
        @param wav_path Chemin WAV relatif.
        @param tts_text Texte si TTS.
        @param fallback_text Texte de secours.
        @returns True si lecture OK.
        """
        audio = self._audio_settings()
        if source == "wav":
            resolved = pick_wav_or_none(self.config, audio, source="wav", wav_path=wav_path)
            if resolved:
                ok = await self._play_wav_file_on_line(
                    resolved,
                    already_in_voice_mode=already_in_voice_mode,
                    recorder=recorder,
                )
                if ok:
                    return True
                logger.warning("Lecture WAV echouee: {} — fallback TTS", resolved)
        text = (tts_text or fallback_text or "").strip()
        if not text:
            return False
        return await self._play_on_line(
            text,
            already_in_voice_mode=already_in_voice_mode,
            recorder=recorder,
        )

    async def _play_on_line(
        self,
        text: str,
        already_in_voice_mode: bool = False,
        recorder: Optional[_IncomingLineRecorder] = None,
    ) -> bool:
        """
        Génère un WAV 8 kHz à partir du texte (TTS) et le joue sur la ligne téléphonique
        (modem mode voix série ou ALSA). Si la synthèse est indisponible, tente de jouer
        un fichier par défaut ivr_wav/ivr_message.wav s'il existe.

        Returns:
            True si la lecture a réussi.
        """
        if not self.modem.is_initialized:
            return False
        if not text:
            return False

        rec = recorder or self._incoming_recorder
        if rec:
            await rec.pause()

        try:
            return await self._play_on_line_unlocked(text, already_in_voice_mode)
        finally:
            if rec:
                await rec.resume(already_in_voice_mode=True)

    async def _play_on_line_unlocked(self, text: str, already_in_voice_mode: bool = False) -> bool:
        """Joue du TTS sur la ligne (appelant doit avoir libéré le flux VRX)."""
        if not self.modem.is_initialized:
            return False
        if not text:
            return False

        # Si TTS indisponible, jouer un WAV par défaut s'il existe
        if not self._voice_available:
            default_wav = self._ensure_ivr_wav_dir() / "ivr_message.wav"
            if default_wav.exists():
                if self._use_modem_voice_serial():
                    return await self.modem.play_wav_via_serial(default_wav, already_in_voice_mode=already_in_voice_mode)
                proc = await asyncio.create_subprocess_exec(
                    "aplay", "-D", self._alsa_play, "-q", str(default_wav),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                return proc.returncode == 0
            return False

        try:
            from pydub import AudioSegment
        except ImportError:
            logger.warning("pydub manquant: pip install pydub pour jouer l'IVR sur la ligne")
            return False

        basename = self._ivr_basename_for_text(text)
        out_wav: Optional[Path] = None
        if basename:
            out_wav = self._ivr_cache.get_if_fresh(text, basename)

        if not out_wav:
            temp_tts = await self.voice_synthesis.speak(
                text,
                rate=getattr(self.config, "edge_tts_rate", "+0%"),
                pitch=getattr(self.config, "edge_tts_pitch", "+0Hz"),
            )
            if not temp_tts or not Path(temp_tts).exists():
                return False
            ivr_dir = self._ensure_ivr_wav_dir()
            out_wav = ivr_dir / f"ivr_live_{hash(text) % 2**31}.wav"
            try:
                segment = AudioSegment.from_file(str(temp_tts))
                thresh = -40.0
                if segment.dBFS != float("-inf"):
                    thresh = max(-45.0, segment.dBFS - 18.0)
                segment = trim_leading_trailing_silence(segment, silence_threshold=thresh, padding_ms=15)
                export_wav_8k_8bit(
                    segment,
                    out_wav,
                    normalize=True,
                    profile=resolve_profile_from_config(self.config),
                )
            except Exception as e:
                logger.exception("Conversion TTS -> WAV 8k: %s", e)
                return False

        if self._use_modem_voice_serial():
            ok = await self.modem.play_wav_via_serial(out_wav, already_in_voice_mode=already_in_voice_mode)
        else:
            proc = await asyncio.create_subprocess_exec(
                "aplay", "-D", self._alsa_play, "-q", str(out_wav),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            ok = proc.returncode == 0
            if not ok and stderr:
                logger.warning("aplay: %s", stderr.decode(errors="ignore"))
        return ok

    async def _record_audio(
        self,
        duration: int,
        already_in_voice_mode: bool = False,
        recorder: Optional[_IncomingLineRecorder] = None,
        *,
        stop_on_remote_hangup: bool = True,
        silence_timeout_sec: float = 0.0,
        persist_wav: Optional[Path] = None,
    ) -> bytes:
        """
        Enregistre l'audio depuis la ligne (modem VRX ou ALSA), puis retourne
        des données PCM 16 kHz 16-bit pour la reconnaissance vocale.

        Args:
            duration: Durée d'enregistrement en secondes
            already_in_voice_mode: True si le modem est déjà en mode voix (après play_wav_via_serial)
            recorder: Enregistreur parallèle entrant (pause / reprise)
            stop_on_remote_hangup: True pour couper si l'appelant raccroche
            silence_timeout_sec: Couper après N secondes de silence (0 = désactivé)
            persist_wav: Si fourni, conserve le WAV 8 kHz (message vocal) au lieu de le supprimer

        Returns:
            Données PCM 16-bit 16 kHz mono (bytes)
        """
        if not self.modem.is_initialized:
            await asyncio.sleep(min(duration, 2))
            return b""
        # Respecte max_call_duration si une deadline est posee.
        if self._call_deadline is not None:
            import time as _time

            remaining = max(1.0, self._call_deadline - _time.monotonic())
            duration = int(min(float(duration), remaining))
        rec = recorder or self._incoming_recorder
        if rec:
            await rec.pause()
        base = Path(self.config.base_path) if self.config.base_path else Path(tempfile.gettempdir())
        recordings_dir = base / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        temp_wav = persist_wav if persist_wav is not None else (recordings_dir / f"call_record_{ts}.wav")
        if persist_wav is not None:
            persist_wav.parent.mkdir(parents=True, exist_ok=True)
        self._log_call(
            "record_debut",
            duree_s=duration,
            hangup=int(stop_on_remote_hangup),
            silence_s=silence_timeout_sec,
        )
        try:
            if self._use_modem_voice_serial():
                ok = await self.modem.record_wav_via_serial(
                    float(duration),
                    temp_wav,
                    already_in_voice_mode=already_in_voice_mode,
                    stop_on_remote_hangup=stop_on_remote_hangup,
                    silence_timeout_sec=silence_timeout_sec,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    "arecord", "-D", self._alsa_record, "-d", str(duration),
                    "-f", "S16_LE", "-r", "16000", "-c", "1", "-q", str(temp_wav),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                ok = proc.returncode == 0 and temp_wav.exists()
            if not ok or not temp_wav.exists():
                self._log_call("record_fin", ok=0, raison=self.modem.last_vrx_stop_reason or "echec")
                return b""
            pcm_bytes = b""
            if rec and temp_wav.exists():
                with wave.open(str(temp_wav), "rb") as wf:
                    pcm_bytes = wf.readframes(wf.getnframes())
                    rec.append_pcm(pcm_bytes)
            self._log_call(
                "record_fin",
                ok=1,
                octets=temp_wav.stat().st_size if temp_wav.exists() else 0,
                raison=self.modem.last_vrx_stop_reason or "ok",
            )
            if self._active_call_monotonic is not None:
                self._pending_call_duration_sec = max(
                    1, int(time.monotonic() - self._active_call_monotonic)
                )
            return load_wav_as_16k16bit_pcm(temp_wav)
        except FileNotFoundError as e:
            logger.warning("arecord/aplay manquant ou modem non prêt: %s", e)
            return b""
        except Exception as e:
            logger.exception("Erreur enregistrement ligne: {}", e)
            return b""
        finally:
            if persist_wav is None and temp_wav.exists():
                try:
                    temp_wav.unlink()
                except OSError:
                    pass
            if rec:
                await rec.resume(already_in_voice_mode=True)

    async def _record_message(self, recorder: Optional[_IncomingLineRecorder] = None):
        """Enregistre un message vocal (jouer bip sur la ligne, enregistrer, rejouer confirmation)."""
        logger.info("Enregistrement d'un message vocal")
        rec = recorder or self._incoming_recorder
        try:
            await self._play_beep_on_line(recorder=rec)
            audio_data = await self._record_audio(
                self.config.voicemail_max_duration,
                already_in_voice_mode=self._use_modem_voice_serial(),
                recorder=rec,
                stop_on_remote_hangup=True,
                silence_timeout_sec=float(getattr(self.config, "voicemail_silence_timeout_sec", 3) or 3),
            )
            if self.current_call_id and audio_data:
                logger.info("Message enregistré (inclus dans l'enregistrement global de l'appel)")
            await self._play_on_line(
                "Message enregistré. Au revoir!",
                already_in_voice_mode=self._use_modem_voice_serial(),
                recorder=rec,
            )
        except Exception as e:
            logger.exception("Erreur lors de l'enregistrement du message: %s", e)
    
    def stop(self):
        """Arrête le gestionnaire d'appels"""
        self.is_running = False
        self.modem.close()
        logger.info("Gestionnaire d'appels arrêté")
