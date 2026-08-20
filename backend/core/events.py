"""
Système d'événements pour VocalGuard
Permet une architecture découplée et extensible
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from enum import Enum
from loguru import logger


class EventType(str, Enum):
    """Types d'événements"""
    CALL_INCOMING = "call.incoming"
    CALL_ANSWERED = "call.answered"
    CALL_BLOCKED = "call.blocked"
    CALL_COMPLETED = "call.completed"
    CALL_MISSED = "call.missed"
    CALL_OUTGOING_DIALING = "call.outgoing.dialing"
    CALL_OUTGOING_CONNECTED = "call.outgoing.connected"
    CALL_OUTGOING_ENDED = "call.outgoing.ended"
    CALL_TRANSCRIPTION_PARTIAL = "call.transcription.partial"
    CALL_TRANSCRIPTION_FINAL = "call.transcription.final"
    CALL_SESSION_LOG = "call.session.log"
    
    VOICEMAIL_RECORDED = "voicemail.recorded"
    VOICEMAIL_DELETED = "voicemail.deleted"
    
    CALLER_BLOCKED = "caller.blocked"
    CALLER_WHITELISTED = "caller.whitelisted"
    
    VOICE_RECOGNITION_STARTED = "voice.recognition.started"
    VOICE_RECOGNITION_COMPLETED = "voice.recognition.completed"
    
    MODEM_CONNECTED = "modem.connected"
    MODEM_DISCONNECTED = "modem.disconnected"
    MODEM_ERROR = "modem.error"

    # Import entreprises (prospection)
    ENTREPRISE_IMPORT_STARTED = "entreprise.import.started"
    ENTREPRISE_IMPORT_PROGRESS = "entreprise.import.progress"
    ENTREPRISE_IMPORT_COMPLETED = "entreprise.import.completed"
    ENTREPRISE_IMPORT_FAILED = "entreprise.import.failed"

    # OSINT (tâches Celery)
    OSINT_PROFILE_COMPLETED = "osint.profile.completed"
    OSINT_PROFILE_FAILED = "osint.profile.failed"


@dataclass
class Event:
    """Représente un événement"""
    event_type: EventType
    timestamp: datetime
    data: Dict[str, Any]
    source: Optional[str] = None
    
    def __post_init__(self):
        """Initialise la date si non fournie"""
        if not isinstance(self.timestamp, datetime):
            self.timestamp = datetime.utcnow()


class EventBus:
    """Bus d'événements pour la communication entre composants"""
    
    def __init__(self):
        """Initialise le bus d'événements"""
        self._handlers: Dict[EventType, List[Callable]] = {}
        self._global_handlers: List[Callable] = []
    
    def subscribe(self, event_type: EventType, handler: Callable):
        """
        Abonne un handler à un type d'événement
        
        Args:
            event_type: Type d'événement
            handler: Fonction à appeler (doit être async)
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        
        self._handlers[event_type].append(handler)
        logger.debug(f"Handler enregistré pour {event_type}")
    
    def subscribe_all(self, handler: Callable):
        """
        Abonne un handler à tous les événements
        
        Args:
            handler: Fonction à appeler pour tous les événements
        """
        self._global_handlers.append(handler)
        logger.debug("Handler global enregistré")
    
    def unsubscribe(self, event_type: EventType, handler: Callable):
        """
        Désabonne un handler
        
        Args:
            event_type: Type d'événement
            handler: Handler à retirer
        """
        if event_type in self._handlers:
            if handler in self._handlers[event_type]:
                self._handlers[event_type].remove(handler)
    
    async def publish(self, event: Event):
        """
        Publie un événement
        
        Args:
            event: Événement à publier
        """
        logger.debug(f"Publication de l'événement: {event.event_type}")
        
        # Appeler les handlers spécifiques
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                await self._call_handler(handler, event)
            except Exception as e:
                logger.exception(f"Erreur dans le handler pour {event.event_type}: {e}")
        
        # Appeler les handlers globaux
        for handler in self._global_handlers:
            try:
                await self._call_handler(handler, event)
            except Exception as e:
                logger.exception(f"Erreur dans le handler global: {e}")
    
    async def _call_handler(self, handler: Callable, event: Event):
        """
        Appelle un handler de manière sécurisée (fonction async, coroutine ou objet avec __call__ async).

        Args:
            handler: Handler à appeler
            event: Événement à passer
        """
        if asyncio.iscoroutinefunction(handler):
            await handler(event)
            return
        result = handler(event)
        if asyncio.iscoroutine(result):
            await result
    
    def clear(self):
        """Efface tous les handlers"""
        self._handlers.clear()
        self._global_handlers.clear()


# Instance globale du bus d'événements
event_bus = EventBus()

