"""
Gestionnaire d'appels - Orchestre le traitement des appels entrants
Version améliorée avec services et événements
"""

import asyncio
import os
import tempfile
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional
from loguru import logger
from sqlalchemy.orm import Session

from backend.core.config import Config
from backend.core.modem_handler import ModemHandler
from backend.core.events import Event, EventType, event_bus
from backend.voice.recognition import VoiceRecognition
from backend.voice.synthesis import VoiceSynthesis
from backend.voice.ivr_patterns import IvrPatternsEngine
from backend.voice.audio_utils import export_wav_8k_8bit, load_wav_as_16k16bit_pcm, trim_leading_trailing_silence, write_beep_wav_8k
from backend.voice.ivr_cache import IvrAudioCache

DEFAULT_VOICEMAIL_GREETING = (
    "Bonjour, Daniel Craft. Absents pour le moment. "
    "Laissez votre message après le bip."
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

    async def start(self, already_in_voice_mode: bool = True) -> None:
        if not self._cm._use_modem_voice_serial():
            return
        ok = await self._cm.modem.start_outgoing_vrx_stream(already_in_voice_mode=already_in_voice_mode)
        if not ok:
            logger.warning("Enregistrement entrant: impossible d'ouvrir VRX")
            return
        self._active = True
        self._stop.clear()
        self._task = asyncio.create_task(self._read_loop(), name="incoming_vrx_recorder")

    async def _read_loop(self) -> None:
        while not self._stop.is_set():
            chunk = await self._cm.modem.read_outgoing_vrx_chunk(2048)
            if chunk:
                self.chunks.append(chunk)
            else:
                await asyncio.sleep(0.02)

    async def pause(self) -> None:
        if not self._active:
            return
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
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
        self._stop.clear()

    async def resume(self, already_in_voice_mode: bool = True) -> None:
        if not self._cm._use_modem_voice_serial():
            return
        ok = await self._cm.modem.start_outgoing_vrx_stream(already_in_voice_mode=already_in_voice_mode)
        if not ok:
            return
        self._active = True
        self._task = asyncio.create_task(self._read_loop(), name="incoming_vrx_recorder")

    def append_pcm(self, data: bytes) -> None:
        if data:
            self.chunks.append(data)

    async def save(self, call_id: int) -> None:
        await self.pause()
        self._active = False
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
        self._voice_available = True  # False si STT ou TTS non disponibles (app demarre quand meme)
        self._recognition_available = False

        # Mode audio modem: voix série (Conexant) ou ALSA. USE_MODEM_VOICE_MODE=0 force ALSA (evite ton aigu).
        _voice_env = os.environ.get("USE_MODEM_VOICE_MODE", "").strip().lower()
        self._force_alsa = _voice_env in ("0", "false", "no")
        self._use_voice_serial = not self._force_alsa and _voice_env in ("1", "true", "yes")
        self._alsa_play = os.environ.get("ALSA_MODEM_DEVICE") or os.environ.get("ALSA_DEVICE", "default")
        self._alsa_record = os.environ.get("ALSA_MODEM_RECORD_DEVICE") or self._alsa_play
        self._ivr_wav_dir: Optional[Path] = None
        self._ivr_cache = IvrAudioCache(config, self.voice_synthesis)
        
        # Enregistrer les handlers d'événements
        self._setup_event_handlers()
    
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
            await self._warmup_ivr_cache()

        logger.info(
            "Gestionnaire d'appels initialisé (STT: %s, TTS: %s)",
            "activée" if self._recognition_available else "désactivée",
            "activée" if self._voice_available else "désactivée",
        )

    def _greeting_text(self) -> str:
        greeting = (self.config.voicemail_greeting or "").strip()
        return greeting or DEFAULT_VOICEMAIL_GREETING

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
        if greeting:
            logger.info("IVR pret: {}", greeting.name)
        if goodbye:
            logger.info("IVR pret: {}", goodbye.name)
        logger.info("IVR pret: {}", beep_path.name)
    
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
    
    async def handle_incoming_call(self, caller_id: Optional[str] = None, caller_name: Optional[str] = None):
        """
        Traite un appel entrant.

        Priorite : saisir la ligne modem des que possible pour couper la sonnerie
        du telephone fixe en parallele (rings=0).

        Args:
            caller_id: Numéro de téléphone de l'appelant
            caller_name: Nom de l'appelant (si disponible)
        """
        if self._incoming_handling:
            if caller_id and self.current_call_id:
                await self.call_service.set_call_caller_info(
                    self.current_call_id,
                    phone_number=caller_id,
                    caller_name=caller_name,
                )
            return

        self._incoming_handling = True
        self._line_already_answered = False
        logger.info(f"Appel entrant de {caller_id} ({caller_name})")

        try:
            if self.config.rings_before_answer > 0:
                await asyncio.sleep(self.config.rings_before_answer * 2)

            # Decrocher en premier : arrete la sonnerie sur le fixe parallele
            fast_seize = self.config.rings_before_answer <= 0 and self.modem.supports_voice_serial
            ok, ata_cid, ata_cname = await self.modem.answer_call(fast_voice_seize=fast_seize)
            self._line_already_answered = ok
            if not caller_id and ata_cid:
                caller_id = ata_cid
            if not caller_name and ata_cname:
                caller_name = ata_cname
            if not ok:
                logger.error("Impossible de decrocher au RING — le fixe peut continuer a sonner")

            call = await self.call_service.create_incoming_call(
                phone_number=caller_id,
                caller_name=caller_name,
            )
            self.current_call_id = call.id

            is_blocked = await self.block_service.is_blocked(caller_id, caller_name)

            if is_blocked:
                logger.info(f"Appel bloqué: {caller_id}")
                await self.call_service.block_call(call.id)
                await self._handle_blocked_call(skip_answer=self._line_already_answered)
            else:
                await self.call_service.answer_call(call.id)
                await self._handle_permitted_call(skip_modem_answer=self._line_already_answered)

        except Exception as e:
            logger.exception(f"Erreur lors du traitement de l'appel: {e}")
            if self.current_call_id:
                await self.call_service.miss_call(self.current_call_id)
        finally:
            self._incoming_handling = False
            self._line_already_answered = False
    
    async def _handle_blocked_call(self, skip_answer: bool = False):
        """Traite un appel bloqué"""
        logger.info("Traitement d'un appel bloqué")
        
        try:
            if not skip_answer:
                ok, _cid, _cname = await self.modem.answer_call()
                if not ok:
                    logger.warning("Impossible de decrocher pour message bloque")
            await self._play_on_line(
                "Désolé, cet appel a été bloqué.",
                already_in_voice_mode=self._use_modem_voice_serial() and skip_answer,
            )
            await self.modem.hangup()
        
        except Exception as e:
            logger.exception(f"Erreur lors du traitement d'un appel bloqué: {e}")
        finally:
            if self.current_call_id:
                await self.call_service.complete_call(self.current_call_id, duration=0)
                self.current_call_id = None
    
    async def _handle_permitted_call(self, skip_modem_answer: bool = False):
        """Traite un appel autorisé"""
        logger.info("Traitement d'un appel autorisé")
        recorder = _IncomingLineRecorder(self)
        self._incoming_recorder = recorder

        try:
            ok = skip_modem_answer
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
            await self._play_on_line(greeting, already_in_voice_mode=True, recorder=None)

            vm_mode = (getattr(self.config, "voicemail_mode", "simple") or "simple").strip().lower()
            vm_simple = self.config.voicemail_enabled and vm_mode != "ivr"

            # Bip tout de suite après l'accueil (avant tout VRX parallèle qui bloque ~30 s).
            if vm_simple:
                await self._play_beep_on_line(recorder=None)
            elif self._use_modem_voice_serial():
                await recorder.start(already_in_voice_mode=True)

            if self.config.voicemail_enabled:
                if vm_mode == "ivr" and self._recognition_available:
                    if not recorder._active:
                        await recorder.start(already_in_voice_mode=True)
                    await self._handle_voice_interaction(recorder=recorder)
                else:
                    await self._handle_voicemail_simple(recorder=recorder, skip_beep=vm_simple)
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

        @param recorder Enregistreur parallèle entrant (optionnel).
        @param skip_beep True si le bip a déjà été joué juste après le message d'accueil.
        """
        logger.info("Mode répondeur simple (bip + enregistrement)")
        rec = recorder or self._incoming_recorder
        try:
            if not skip_beep:
                await self._play_beep_on_line(recorder=rec)
            audio_data = await self._record_audio(
                duration=self.config.voicemail_max_duration,
                already_in_voice_mode=self._use_modem_voice_serial(),
                recorder=rec,
                stop_on_remote_hangup=True,
                silence_timeout_sec=float(getattr(self.config, "voicemail_silence_timeout_sec", 5) or 0),
            )
            if audio_data:
                logger.info("Message répondeur capturé (%s octets PCM)", len(audio_data))
            await self._play_on_line(
                VOICEMAIL_GOODBYE,
                already_in_voice_mode=self._use_modem_voice_serial(),
                recorder=rec,
            )
        except Exception as e:
            logger.exception("Erreur mode répondeur simple: %s", e)

    async def _play_beep_on_line(self, recorder: Optional[_IncomingLineRecorder] = None) -> bool:
        """
        Joue un bip court sur la ligne (WAV 8 kHz généré localement).

        @param recorder Enregistreur entrant à mettre en pause pendant le bip.
        @returns True si la lecture a réussi.
        """
        if not self.modem.is_initialized:
            return False
        ivr_dir = self._ensure_ivr_wav_dir()
        beep_path = ivr_dir / "voicemail_beep.wav"
        write_beep_wav_8k(beep_path)
        rec = recorder or self._incoming_recorder
        if rec:
            await rec.pause()
        try:
            if self._use_modem_voice_serial():
                return await self.modem.play_wav_via_serial(beep_path, already_in_voice_mode=True)
            proc = await asyncio.create_subprocess_exec(
                "aplay", "-D", self._alsa_play, "-q", str(beep_path),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        finally:
            if rec:
                await rec.resume(already_in_voice_mode=True)

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
                silence_timeout_sec=float(getattr(self.config, "voicemail_silence_timeout_sec", 5) or 0),
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
                rate=getattr(self.config, "edge_tts_rate", "+12%"),
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

        Returns:
            Données PCM 16-bit 16 kHz mono (bytes)
        """
        if not self.modem.is_initialized:
            await asyncio.sleep(min(duration, 2))
            return b""
        rec = recorder or self._incoming_recorder
        if rec:
            await rec.pause()
        base = Path(self.config.base_path) if self.config.base_path else Path(tempfile.gettempdir())
        recordings_dir = base / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        temp_wav = recordings_dir / f"call_record_{ts}.wav"
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
            if temp_wav.exists():
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
                silence_timeout_sec=float(getattr(self.config, "voicemail_silence_timeout_sec", 5) or 0),
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
