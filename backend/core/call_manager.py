"""
Gestionnaire d'appels - Orchestre le traitement des appels entrants
Version améliorée avec services et événements
"""

import asyncio
from datetime import datetime
from typing import Optional
from loguru import logger
from sqlalchemy.orm import Session

from backend.core.config import Config
from backend.core.modem_handler import ModemHandler
from backend.core.events import Event, EventType, event_bus
from backend.voice.recognition import VoiceRecognition
from backend.voice.synthesis import VoiceSynthesis
from backend.services.call_service import CallService
from backend.services.block_service import BlockService
from backend.services.conversation_service import ConversationService
from backend.database.database import get_db
from backend.ai.ollama_client import OllamaClient


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
        
        # Services
        self.call_service = CallService(db)
        self.block_service = BlockService(config, db)
        self.conversation_service = ConversationService(self.ollama_client)
        
        # Client Ollama (optionnel)
        self.ollama_client = None
        try:
            self.ollama_client = OllamaClient()
            if self.ollama_client.test_connection():
                logger.info(f"Ollama activé - Modèle: {self.ollama_client.model}")
            else:
                logger.warning("Ollama configuré mais non disponible")
                self.ollama_client = None
        except Exception as e:
            logger.warning(f"Ollama non disponible: {e}")
            self.ollama_client = None
        
        self.is_running = False
        self.current_call_id: Optional[int] = None
        
        # Enregistrer les handlers d'événements
        self._setup_event_handlers()
    
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
        
        # Initialiser le modem (optionnel)
        modem_initialized = await self.modem.initialize()
        if not modem_initialized:
            logger.warning("Modem non disponible - l'API fonctionnera sans gestion d'appels")
        else:
            # Configurer le callback du modem pour les appels entrants
            self.modem.on_incoming_call = self.handle_incoming_call
            logger.info("Modem initialisé")
        
        # Initialiser la reconnaissance vocale
        await self.voice_recognition.initialize()
        
        # Initialiser la synthèse vocale
        await self.voice_synthesis.initialize()
        
        logger.info("Gestionnaire d'appels initialisé")
    
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
        Traite un appel entrant
        
        Args:
            caller_id: Numéro de téléphone de l'appelant
            caller_name: Nom de l'appelant (si disponible)
        """
        logger.info(f"Appel entrant de {caller_id} ({caller_name})")
        
        try:
            # Créer l'enregistrement d'appel via le service
            call = await self.call_service.create_incoming_call(
                phone_number=caller_id,
                caller_name=caller_name
            )
            self.current_call_id = call.id
            
            # Vérifier si l'appelant est bloqué
            is_blocked = await self.block_service.is_blocked(caller_id, caller_name)
            
            if is_blocked:
                logger.info(f"Appel bloqué: {caller_id}")
                await self.call_service.block_call(call.id)
                await self._handle_blocked_call()
            else:
                # Attendre le nombre de sonneries configuré
                await asyncio.sleep(self.config.rings_before_answer * 2)  # ~2 secondes par sonnerie
                
                # Décrocher et traiter l'appel
                await self.call_service.answer_call(call.id)
                await self._handle_permitted_call()
        
        except Exception as e:
            logger.exception(f"Erreur lors du traitement de l'appel: {e}")
            if self.current_call_id:
                await self.call_service.miss_call(self.current_call_id)
    
    async def _handle_blocked_call(self):
        """Traite un appel bloqué"""
        logger.info("Traitement d'un appel bloqué")
        
        try:
            # Décrocher brièvement pour jouer le message
            await self.modem.answer_call()
            
            # Jouer le message de blocage
            await self.voice_synthesis.speak("Désolé, cet appel a été bloqué.")
            
            # Raccrocher immédiatement
            await self.modem.hangup()
        
        except Exception as e:
            logger.exception(f"Erreur lors du traitement d'un appel bloqué: {e}")
        finally:
            if self.current_call_id:
                await self.call_service.complete_call(self.current_call_id, duration=0)
                self.current_call_id = None
    
    async def _handle_permitted_call(self):
        """Traite un appel autorisé"""
        logger.info("Traitement d'un appel autorisé")
        
        try:
            # Décrocher
            if not await self.modem.answer_call():
                logger.error("Impossible de décrocher")
                if self.current_call_id:
                    await self.call_service.miss_call(self.current_call_id)
                return
            
            # Jouer le message d'accueil
            greeting = "Bonjour, vous êtes bien connecté à VocalGuard. Que puis-je faire pour vous?"
            await self.voice_synthesis.speak(greeting)
            
            # Écouter la réponse de l'appelant
            if self.config.voicemail_enabled:
                await self._handle_voice_interaction()
            else:
                # Mode simple: enregistrer directement le message
                await self._record_message()
        
        except Exception as e:
            logger.exception(f"Erreur lors du traitement d'un appel autorisé: {e}")
            await self.voice_synthesis.speak("Désolé, une erreur s'est produite. Au revoir.")
        finally:
            await self.modem.hangup()
            if self.current_call_id:
                start_time = datetime.utcnow()
                # Calculer la durée approximative
                duration = None  # TODO: Calculer la durée réelle
                await self.call_service.complete_call(self.current_call_id, duration=duration)
                self.current_call_id = None
    
    async def _handle_voice_interaction(self):
        """Gère l'interaction vocale avec l'appelant"""
        logger.info("Démarrage de l'interaction vocale")
        
        try:
            # Enregistrer l'audio de l'appelant
            audio_data = await self._record_audio(duration=self.config.voicemail_max_duration)
            
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
            
            # Transcrire la parole
            transcription = await self.voice_recognition.transcribe(audio_data)
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
            
            # Traiter la commande vocale
            response = await self._process_voice_command(transcription)
            
            # Répondre vocalement
            if response:
                await self.voice_synthesis.speak(response)
        
        except Exception as e:
            logger.exception(f"Erreur lors de l'interaction vocale: {e}")
            await self.voice_synthesis.speak("Désolé, je n'ai pas compris. Veuillez laisser un message après le bip.")
            await self._record_message()
    
    async def _process_voice_command(self, transcription: str) -> Optional[str]:
        """
        Traite une commande vocale avec Ollama si disponible
        
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
            if self.ollama_client:
                self.ollama_client.clear_history()  # Effacer l'historique à la fin de l'appel
            return "Au revoir, bonne journée!"
        
        # Deleguer la generation de reponse au service de conversation
        try:
            reply = await self.conversation_service.generate_reply(transcription)
            if reply:
                return reply
        except Exception as e:
            logger.warning(f"Erreur dans le service de conversation, fallback vers reponse par defaut: {e}")
        
        # Fallback: réponse par défaut
        return "Je n'ai pas bien compris. Voulez-vous laisser un message?"
    
    async def _record_audio(self, duration: int) -> bytes:
        """
        Enregistre l'audio depuis le modem
        
        Args:
            duration: Durée d'enregistrement en secondes
            
        Returns:
            Données audio brutes
        """
        # TODO: Implémenter l'enregistrement audio depuis le modem
        # Pour l'instant, retourner des données vides
        await asyncio.sleep(duration)
        return b""
    
    async def _record_message(self):
        """Enregistre un message vocal"""
        logger.info("Enregistrement d'un message vocal")
        
        try:
            await self.voice_synthesis.speak("Veuillez laisser votre message après le bip.")
            
            # Enregistrer le message
            audio_data = await self._record_audio(self.config.voicemail_max_duration)
            
            # Sauvegarder le message via le service
            if self.current_call_id and audio_data:
                # TODO: Implémenter la sauvegarde du message vocal
                logger.info("Message enregistré")
            
            await self.voice_synthesis.speak("Message enregistré. Au revoir!")
        
        except Exception as e:
            logger.exception(f"Erreur lors de l'enregistrement du message: {e}")
    
    def stop(self):
        """Arrête le gestionnaire d'appels"""
        self.is_running = False
        self.modem.close()
        logger.info("Gestionnaire d'appels arrêté")
