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
from backend.core.modem_handler import ModemHandler
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
    trim_leading_trailing_silence,
    tts_source_to_modem_wav,
    write_beep_wav_8k,
)
from backend.voice.ivr_cache import IvrAudioCache

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

    async def start(self, already_in_voice_mode: bool = True) -> None:
        if not self._cm._use_modem_voice_serial():
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
        if data:
            self.chunks.append(data)

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
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(1)
            wf.setframerate(8000)
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

    async def request_ui_hangup(self, call_id: int) -> bool:
        """
        Raccrochage demande depuis l'UI pendant un appel entrant actif.

        @param call_id Identifiant de l'appel en cours.
        @returns True si la demande est acceptee (idempotent si autre appel).
        """
        if self.current_call_id is not None and int(call_id) != int(self.current_call_id):
            return True
        logger.info("Raccrochage UI pour appel {}", call_id)
        self.modem._voice_abort = True
        try:
            await self.modem.hangup()
        except Exception as exc:
            logger.warning("Raccrochage UI modem: {}", exc)
        return True
    
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
        if self.config.use_telephony_daemon:
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

        # Initialiser la reconnaissance vocale (optionnel : si absent, pas de transcription IVR)
        try:
            await self.voice_recognition.initialize()
            self._recognition_available = self.voice_recognition.engine in ("whisper", "vosk")
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
        greeting = await self._ivr_cache.ensure(self._greeting_text(), "voicemail_greeting")
        goodbye = await self._ivr_cache.ensure(VOICEMAIL_GOODBYE, "voicemail_goodbye")
        beep_path = self._ensure_ivr_wav_dir() / "voicemail_beep.wav"
        write_beep_wav_8k(beep_path)
        system_beep = Path(self.config.base_path or ".") / "resources" / "voice" / "system" / "beep.wav"
        if not system_beep.is_file():
            write_beep_wav_8k(system_beep)
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

        voice_wav = await self._ivr_cache.ensure(greeting, "voicemail_greeting")
        if not voice_wav or not voice_wav.is_file():
            raise RuntimeError("Generation TTS accueil echouee")

        active_path = greeting_modem_active_wav_path(self.config)
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
        if not active_path.is_file() or active_path.stat().st_size < 2000:
            raise RuntimeError("Mix accueil modem vide ou absent")

        regenerated_at = _write_greeting_modem_active_meta(self.config, settings, greeting)
        await self._ivr_cache.ensure(VOICEMAIL_GOODBYE, "voicemail_goodbye")
        beep_path = ivr_dir / "voicemail_beep.wav"
        write_beep_wav_8k(beep_path)
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
        voice_gain = float(getattr(audio, "greeting_intro_voice_gain_db", 5.0) or 5.0)
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
        try:
            m.instant_seize_cid_grace_sec = float(
                getattr(self.config, "instant_seize_cid_grace_sec", 0.35) or 0.35
            )
        except (TypeError, ValueError):
            m.instant_seize_cid_grace_sec = 0.35
        self._refresh_instant_ring_seize()

    def _refresh_instant_ring_seize(self) -> None:
        """Active le seize sync au RING si repondeur + rings=0 effectifs (policy)."""
        auto = bool(getattr(self.config, "incoming_auto_answer", True))
        whitelist_ring_only = bool(getattr(self.config, "whitelist_ring_only", False))
        min_answer_rings = int(getattr(self.config, "rings_before_answer", 0) or 0)
        if hasattr(self, "incoming_policy"):
            answer_rings: list[int] = []
            for profile in ("screened", "blocked", "permitted"):
                resolved = resolve_profile_decision(self.incoming_policy.settings, profile)  # type: ignore[arg-type]
                if "answer" in resolved.actions:
                    answer_rings.append(int(resolved.rings_before_answer))
            if answer_rings:
                min_answer_rings = min(answer_rings)
        self.modem.instant_ring_seize = bool(
            auto and min_answer_rings <= 0 and not whitelist_ring_only
        )
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
        greeting = greeting_text(self.config, settings)
        active = greeting_modem_active_wav_path(self.config)
        if active.is_file() and is_greeting_modem_active_fresh(self.config, settings, greeting):
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

        @param caller_id Numero.
        @param caller_name Nom CID.
        @param rings Sonneries configurees pour l'attente.
        @param reason Motif log (policy ignore, mode telephone).
        """
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
        outcome = await self._wait_phone_mode_rings_end(max_wait_sec=wait_sec)
        caller_id = self._pending_cid or caller_id
        caller_name = self._pending_cname or caller_name
        if caller_id or caller_name:
            await self.call_service.set_call_caller_info(
                call.id, phone_number=caller_id, caller_name=caller_name
            )
        await self.call_service.miss_call(call.id)
        logger.info("Fin journalisation appel #{} ({})", call.id, outcome)
        self.current_call_id = None

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

        try:
            auto_answer_cfg = apply_schedule_to_auto_answer(self.config)
            rings = int(getattr(self.config, "rings_before_answer", 0) or 0)
            whitelist_ring_only = bool(getattr(self.config, "whitelist_ring_only", False))
            cid_wait = float(getattr(self.config, "cid_wait_sec", 2.5) or 2.5)
            timed_out = False

            need_cid_before_action = (
                not auto_answer_cfg
                or rings > 0
                or (auto_answer_cfg and whitelist_ring_only)
            )
            immediate_answer = bool(
                auto_answer_cfg and rings <= 0 and not need_cid_before_action
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
                logger.info("Repondeur: seize sync deja fait au RING (ok={})", ok)
                if not ok:
                    ok, ata_cid, ata_cname = await self.modem.answer_call(fast_voice_seize=True)
            else:
                fast_seize = rings <= 0 and auto_answer and self.modem.supports_voice_serial
                ok, ata_cid, ata_cname = await self.modem.answer_call(fast_voice_seize=fast_seize)
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
            self._arm_call_deadline()
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
                logger.info("Appel bloqué: {}", caller_id)
                await self.call_service.block_call(call.id)
                await self._handle_blocked_call(skip_answer=True)
            else:
                await self.call_service.answer_call(call.id)
                await self._handle_permitted_call(skip_modem_answer=True, line_answered=ok)

        except Exception as e:
            logger.exception("Erreur lors du traitement de l'appel: {}", e)
            if self.current_call_id:
                await self.call_service.miss_call(self.current_call_id)
        finally:
            self._incoming_handling = False
            self._line_already_answered = False
            self._pending_cid = None
            self._pending_cname = None
            self._cid_event = None
            self._cname_event = None
            self._phone_mode_ring_event = None
            self._call_deadline = None
            self._current_incoming_decision = None
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
            await self.modem.hangup()
        
        except Exception as e:
            logger.exception(f"Erreur lors du traitement d'un appel bloqué: {e}")
        finally:
            if self.current_call_id:
                await self.call_service.complete_call(self.current_call_id, duration=0)
                self.current_call_id = None
    
    async def _handle_permitted_call(
        self,
        skip_modem_answer: bool = False,
        *,
        line_answered: bool = True,
    ):
        """Traite un appel autorisé"""
        logger.info("Traitement d'un appel autorisé")
        recorder = _IncomingLineRecorder(self)
        self._incoming_recorder = recorder

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
            early_mode = bool(getattr(self.modem, "early_greeting_was_scheduled", lambda: False)())
            await self.modem.wait_early_greeting_done()
            played = bool(getattr(self.modem, "_greeting_played_on_seize", False))
            interrupted = bool(getattr(self.modem, "_playback_interrupted", False))
            if played and not interrupted:
                logger.info("Accueil deja joue au seize — suite repondeur")
            elif early_mode:
                if not played:
                    logger.warning("Accueil immediat echoue — un seul reessai apres reprise ligne")
                    self.modem._playback_interrupted = False
                    self.modem._voice_abort = False
                    await self.modem.prepare_voice_line_after_seize()
                    played = await self._play_greeting_sequence(
                        greeting=greeting,
                        audio=audio,
                        already_in_voice_mode=True,
                        recorder=None,
                    )
                    interrupted = bool(getattr(self.modem, "_playback_interrupted", False))
            else:
                played = await self._play_greeting_sequence(
                    greeting=greeting,
                    audio=audio,
                    already_in_voice_mode=True,
                    recorder=None,
                )
            if not played and skip_modem_answer and not early_mode:
                logger.warning("Accueil echoue apres seize — reprise ligne voix puis nouvel essai")
                await self.modem.prepare_voice_line_after_seize()
                played = await self._play_greeting_sequence(
                    greeting=greeting,
                    audio=audio,
                    already_in_voice_mode=True,
                    recorder=None,
                )
            # Call screening : si le fixe a pris pendant l'accueil, on coupe et on laisse la ligne.
            if interrupted or played is False:
                logger.info("Accueil interrompu (tel parallele / hangup) — fin sans repondeur")
                if self.current_call_id:
                    await self.call_service.complete_call(self.current_call_id, duration=None)
                    self.current_call_id = None
                return

            if self._call_deadline_exceeded():
                logger.warning("max_call_duration atteint juste apres accueil")
                return

            vm_mode = (getattr(self.config, "voicemail_mode", "simple") or "simple").strip().lower()
            vm_simple = self.config.voicemail_enabled and vm_mode != "ivr"

            if self.config.voicemail_enabled:
                decision = getattr(self, "_current_incoming_decision", None)
                if self._needs_dtmf_gate(decision):
                    if not await self._run_dtmf_gate():
                        logger.info("Filtre DTMF non valide — fin sans enregistrement")
                        return
                if vm_mode == "ivr" and self._recognition_available:
                    if self._use_modem_voice_serial():
                        await recorder.start(already_in_voice_mode=True)
                    await self._handle_voice_interaction(recorder=recorder)
                else:
                    # Un seul bip, juste avant l'enregistrement (pas avant + dedans).
                    await self._handle_voicemail_simple(recorder=recorder, skip_beep=False)
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
            if self.current_call_id:
                try:
                    await recorder.save(self.current_call_id)
                except Exception as exc:
                    logger.warning("Sauvegarde enregistrement entrant: {}", exc)
            await self.modem.hangup()
            if self.current_call_id:
                duration = None  # Peut être enrichi via answer_time/end_time en base
                await self.call_service.complete_call(self.current_call_id, duration=duration)
                self.current_call_id = None
            self._incoming_recorder = None
    
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
        logger.info("Mode répondeur simple (bip + enregistrement)")
        rec = recorder or self._incoming_recorder
        vm = self._voicemail_settings()
        max_duration = int(vm.max_record_sec or self.config.voicemail_max_duration)
        silence_sec = float(
            vm.silence_end_sec
            or getattr(self.config, "voicemail_silence_timeout_sec", 3)
            or 3
        )
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

            audio_data = await self._record_audio(
                duration=max_duration,
                already_in_voice_mode=self._use_modem_voice_serial(),
                recorder=rec,
                stop_on_remote_hangup=True,
                silence_timeout_sec=silence_sec,
                persist_wav=persist_path,
            )
            if audio_data:
                logger.info("Message répondeur capturé (%s octets PCM STT)", len(audio_data))

            if persist_path.exists() and persist_path.stat().st_size >= 4000:
                duration_sec = max(1, int(persist_path.stat().st_size / 8000))
                phone = None
                cname = None
                if self.current_call_id:
                    call_row = self.call_service.call_repo.get_by_id(self.current_call_id)
                    if call_row:
                        phone = call_row.phone_number
                        cname = call_row.caller_name
                vm = await self.call_service.save_voicemail(
                    wav_rel,
                    call_id=self.current_call_id,
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
            elif persist_path.exists():
                logger.info("Message trop court ignore ({})", persist_path.name)
                try:
                    persist_path.unlink()
                except OSError:
                    pass

            if self.modem.remote_hangup_detected():
                logger.info("Appelant a raccroche — fin immediate sans message de fin")
            else:
                await self._play_on_line(
                    VOICEMAIL_GOODBYE,
                    already_in_voice_mode=self._use_modem_voice_serial(),
                    recorder=rec,
                )
        except Exception as e:
            logger.exception("Erreur mode répondeur simple: %s", e)

    async def _transcribe_voicemail_async(self, voicemail_id: int, audio_pcm_16k: bytes) -> None:
        """
        Transcrit un message vocal (STT) sans bloquer la ligne telephonique.

        @param voicemail_id ID du message en base.
        @param audio_pcm_16k PCM 16 kHz 16-bit mono (sortie de ``_record_audio``).
        """
        try:
            text = await self.voice_recognition.transcribe(audio_pcm_16k, sample_rate=16000)
            text = (text or "").strip()
            if not text:
                logger.info("STT message #{} : vide / inaudible", voicemail_id)
                return
            await self.call_service.set_voicemail_transcription(voicemail_id, text)
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
            return await self.modem.send_dtmf("1")
        configured = beep_wav_path(self.config, audio)
        beep_path = configured or (self._ensure_ivr_wav_dir() / "voicemail_beep.wav")
        if not beep_path.is_file():
            write_beep_wav_8k(beep_path)
        if self._use_modem_voice_serial():
            await self.modem.prepare_voice_line_after_seize()
        return await self._play_wav_file_on_line(
            beep_path,
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
        rec = recorder or self._incoming_recorder
        if rec:
            await rec.pause()
        try:
            if self._use_modem_voice_serial():
                return await self.modem.play_wav_via_serial(
                    wav_path, already_in_voice_mode=already_in_voice_mode
                )
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
        voice_gain = float(getattr(audio, "greeting_intro_voice_gain_db", 5.0) or 5.0)
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
        voice_gain = float(getattr(audio, "greeting_intro_voice_gain_db", 5.0) or 5.0)
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
        if self._use_modem_voice_serial() and already_in_voice_mode:
            if not getattr(self.modem, "_voice_line_ready", False):
                await self.modem.prepare_voice_line_after_seize()

        cached_active = self._resolve_early_greeting_wav_path()
        if cached_active and cached_active.is_file():
            logger.info("Accueil cache modem: {}", cached_active.name)
            return await self._play_wav_file_on_line(
                cached_active,
                already_in_voice_mode=already_in_voice_mode,
                recorder=recorder,
            )

        intro = greeting_intro_path(self.config, audio)
        greeting_wav = await self._resolve_greeting_modem_wav(greeting, audio)
        intro_mode = str(getattr(audio, "greeting_intro_mode", "none") or "none")
        if intro and intro.is_file() and greeting_wav and greeting_wav.is_file():
            intro_ms = int(float(getattr(audio, "greeting_intro_sec", 3.2) or 3.2) * 1000)
            crossfade_ms = int(float(getattr(audio, "greeting_intro_crossfade_ms", 520) or 520))
            bed_db = float(getattr(audio, "greeting_intro_voice_bed_db", -24.0) or -24.0)
            if bed_db > -1.0:
                bed_db = None
            voice_gain = float(getattr(audio, "greeting_intro_voice_gain_db", 5.0) or 5.0)
            intro_variant = str(getattr(audio, "greeting_intro_variant", "sting_marimba") or "sting_marimba")
            bed_variant = (
                getattr(audio, "greeting_intro_bed_variant", None)
                or default_bed_variant_for_jingle(intro_variant)
            )
            if intro_mode == "track":
                try:
                    combined = await self._ensure_track_greeting_wav(
                        intro,
                        greeting_wav,
                        audio,
                        greeting,
                    )
                    logger.info("Accueil combine (piste): musique + voix -> {}", combined.name)
                    return await self._play_wav_file_on_line(
                        combined,
                        already_in_voice_mode=already_in_voice_mode,
                        recorder=recorder,
                    )
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
                    return await self._play_wav_file_on_line(
                        combined,
                        already_in_voice_mode=already_in_voice_mode,
                        recorder=recorder,
                    )
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
                return False
            already_in_voice_mode = True

        return await self._play_configured_message(
            source=audio.greeting_source,
            wav_path=audio.greeting_wav_path,
            tts_text=greeting,
            fallback_text=greeting,
            already_in_voice_mode=already_in_voice_mode,
            recorder=recorder,
        )

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
            tts_source_to_modem_wav(Path(temp_tts), out_wav)
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
                export_wav_8k_8bit(segment, out_wav, normalize=True)
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
                return b""
            pcm_bytes = b""
            if rec and temp_wav.exists():
                with wave.open(str(temp_wav), "rb") as wf:
                    pcm_bytes = wf.readframes(wf.getnframes())
                    rec.append_pcm(pcm_bytes)
            return load_wav_as_16k16bit_pcm(temp_wav)
        except FileNotFoundError as e:
            logger.warning("arecord/aplay manquant ou modem non prêt: %s", e)
            return b""
        except Exception as e:
            logger.exception("Erreur enregistrement ligne: %s", e)
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
