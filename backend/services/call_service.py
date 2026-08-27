"""
Service de gestion des appels.

Ce module cree, met a jour et journalise les appels dans la base
et publie les evenements associes. Il est egalement responsable
de declencher l'enrichissement OSINT des numeros via les
services adequats.
"""

from typing import Optional
from datetime import datetime
import asyncio
from sqlalchemy.orm import Session
from loguru import logger

from backend.repositories.call_repository import CallRepository
from backend.repositories.caller_repository import CallerRepository
from backend.repositories.voicemail_repository import VoicemailRepository
from backend.core.events import Event, EventType, event_bus
from backend.database.models import Call, Voicemail
from backend.core.config import Config

from backend.osint.services import PhoneOsintService
from backend.services.phone_identity import is_unidentified_phone, normalize_phone_label


class CallService:
    """Service pour la gestion des appels."""
    
    def __init__(self, db: Session):
        """
        Initialise le service d'appels.
        
        Args:
            db: Session de base de donnees.
        """
        self.call_repo = CallRepository(db)
        self.caller_repo = CallerRepository(db)
        self.voicemail_repo = VoicemailRepository(db)
        self.db = db
        
        # Service d'enrichissement OSINT des numeros
        config = Config()
        self.phone_osint_service = PhoneOsintService(db, config)
    
    async def create_incoming_call(
        self,
        phone_number: Optional[str] = None,
        caller_name: Optional[str] = None
    ) -> Call:
        """
        Crée un nouvel appel entrant
        
        Args:
            phone_number: Numéro de téléphone
            caller_name: Nom de l'appelant
            
        Returns:
            Appel cree
        """
        # Chercher ou creer l'appelant uniquement si numero identifiable.
        caller = None
        phone = normalize_phone_label(phone_number)
        if phone and not is_unidentified_phone(phone):
            caller = self.caller_repo.get_by_phone_number(phone)
            if not caller:
                caller = self.caller_repo.create(
                    phone_number=phone,
                    name=caller_name,
                    is_blocked=False,
                    is_whitelisted=False,
                )
        else:
            phone = None

        call = self.call_repo.create_call(
            phone_number=phone,
            caller_name=caller_name,
            caller_id=caller.id if caller else None,
            status="ringing",
        )

        if phone:
            # OSINT hors chemin critique (ne doit jamais retarder un decrochage).
            caller_fk = caller.id if caller else None
            phone_copy = phone

            async def _osint_bg() -> None:
                try:
                    await asyncio.to_thread(
                        self.phone_osint_service.ensure_profile_for_number,
                        phone_copy,
                        caller_fk,
                    )
                except Exception as exc:
                    logger.warning("OSINT background pour {}: {}", phone_copy, exc)

            try:
                asyncio.create_task(_osint_bg(), name=f"osint_call_{call.id}")
            except Exception as exc:
                logger.warning(f"Impossible de planifier l'OSINT pour {phone}: {exc}")

        await event_bus.publish(
            Event(
                event_type=EventType.CALL_INCOMING,
                timestamp=datetime.utcnow(),
                data={
                    "call_id": call.id,
                    "phone_number": phone,
                    "caller_name": caller_name,
                },
                source="CallService",
            )
        )

        logger.info(f"Appel entrant cree: {call.id} ({phone})")
        return call

    async def create_outgoing_call(self, phone_number: str) -> Call:
        """
        Cree un appel sortant initialise en statut dialing.

        @param phone_number Numero compose.
        @returns Appel cree.
        """
        phone = normalize_phone_label(phone_number)
        if not phone or is_unidentified_phone(phone):
            raise ValueError("Numero sortant invalide ou non identifiable.")

        caller = self.caller_repo.get_by_phone_number(phone)
        if not caller:
            caller = self.caller_repo.create(
                phone_number=phone,
                name="Sortant",
                is_blocked=False,
                is_whitelisted=False,
            )

        call = self.call_repo.create_call(
            phone_number=phone,
            caller_name="Sortant",
            caller_id=caller.id,
            status="dialing",
        )
        await event_bus.publish(
            Event(
                event_type=EventType.CALL_OUTGOING_DIALING,
                timestamp=datetime.utcnow(),
                data={"call_id": call.id, "phone_number": phone},
                source="CallService",
            )
        )
        logger.info("Appel sortant cree: {} ({})", call.id, phone)
        return call

    def _discard_unidentified_call(self, call: Call) -> bool:
        """
        Anciennement: supprimait les appels sans CID.
        Desactive: on garde l'historique (affiche "Inconnu" dans l'UI).

        @param call Appel a evaluer.
        @returns Toujours False (jamais supprime).
        """
        if is_unidentified_phone(call.phone_number):
            logger.info(
                "Appel sans numero conserve (id={}) — plus de suppression auto",
                call.id,
            )
        return False
    
    async def answer_call(self, call_id: int) -> Optional[Call]:
        """
        Marque un appel comme répondu
        
        Args:
            call_id: ID de l'appel
            
        Returns:
            Appel mis à jour ou None si non trouvé
        """
        call = self.call_repo.get_by_id(call_id)
        if not call:
            return None
        
        call = self.call_repo.update(call_id, status="answered", answer_time=datetime.utcnow())
        
        # Publier l'événement
        await event_bus.publish(Event(
            event_type=EventType.CALL_ANSWERED,
            timestamp=datetime.utcnow(),
            data={
                "call_id": call_id,
                "phone_number": call.phone_number,
                "caller_name": call.caller_name,
            },
            source="CallService"
        ))
        
        return call
    
    async def complete_call(self, call_id: int, duration: Optional[int] = None) -> Optional[Call]:
        """
        Marque un appel comme terminé
        
        Args:
            call_id: ID de l'appel
            duration: Durée de l'appel en secondes
            
        Returns:
            Appel mis à jour ou None si non trouvé
        """
        call = self.call_repo.get_by_id(call_id)
        if not call:
            return None
        
        update_data = {
            "status": "completed",
            "end_time": datetime.utcnow()
        }
        
        if duration:
            update_data["duration"] = duration
        
        call = self.call_repo.update(call_id, **update_data)

        await event_bus.publish(Event(
            event_type=EventType.CALL_COMPLETED,
            timestamp=datetime.utcnow(),
            data={"call_id": call_id, "duration": duration},
            source="CallService"
        ))

        if call and self._discard_unidentified_call(call):
            return None
        return call
    
    async def block_call(self, call_id: int) -> Optional[Call]:
        """
        Marque un appel comme bloqué
        
        Args:
            call_id: ID de l'appel
            
        Returns:
            Appel mis à jour ou None si non trouvé
        """
        call = self.call_repo.get_by_id(call_id)
        if not call:
            return None
        
        call = self.call_repo.update(call_id, status="blocked", end_time=datetime.utcnow())
        
        # Bloquer l'appelant si possible
        if call.phone_number:
            self.caller_repo.block_caller(call.phone_number)
        
        # Publier l'événement
        await event_bus.publish(Event(
            event_type=EventType.CALL_BLOCKED,
            timestamp=datetime.utcnow(),
            data={"call_id": call_id, "phone_number": call.phone_number},
            source="CallService"
        ))
        
        return call
    
    async def miss_call(self, call_id: int) -> Optional[Call]:
        """
        Marque un appel comme manqué
        
        Args:
            call_id: ID de l'appel
            
        Returns:
            Appel mis à jour ou None si non trouvé
        """
        call = self.call_repo.get_by_id(call_id)
        if not call:
            return None
        
        call = self.call_repo.update(call_id, status="missed", end_time=datetime.utcnow())

        await event_bus.publish(Event(
            event_type=EventType.CALL_MISSED,
            timestamp=datetime.utcnow(),
            data={"call_id": call_id},
            source="CallService"
        ))

        if call and self._discard_unidentified_call(call):
            return None
        return call

    async def set_audio_file(self, call_id: int, audio_file: Optional[str]) -> Optional[Call]:
        """Enregistre le chemin relatif (ex. recordings/...) du WAV d'appel."""
        call = self.call_repo.get_by_id(call_id)
        if not call:
            return None
        return self.call_repo.update(call_id, audio_file=audio_file)

    async def set_transcription_and_intent(
        self,
        call_id: int,
        transcription: Optional[str] = None,
        intent_name: Optional[str] = None,
    ) -> Optional[Call]:
        """
        Met a jour la transcription et/ou l'intent IVR associe a un appel.

        - transcription est stockee dans Call.transcription
        - intent_name est stocke dans Call.ivr_intent (colonne, plus JSON)
        """
        call = self.call_repo.get_by_id(call_id)
        if not call:
            return None

        update_data: dict = {}
        if transcription is not None:
            update_data["transcription"] = transcription

        if intent_name:
            update_data["ivr_intent"] = str(intent_name)[:100]

        if not update_data:
            return call

        call = self.call_repo.update(call_id, **update_data)
        return call

    async def set_call_caller_info(
        self,
        call_id: int,
        phone_number: Optional[str] = None,
        caller_name: Optional[str] = None,
    ) -> Optional[Call]:
        """Met a jour le numero / nom et rattache le Caller via FK."""
        call = self.call_repo.get_by_id(call_id)
        if not call:
            return None
        update_data: dict = {}
        if phone_number is not None:
            phone = normalize_phone_label(phone_number)
            if phone and not is_unidentified_phone(phone):
                update_data["phone_number"] = phone
                caller = self.caller_repo.get_by_phone_number(phone)
                if not caller:
                    caller = self.caller_repo.create(
                        phone_number=phone,
                        name=caller_name,
                        is_blocked=False,
                        is_whitelisted=False,
                    )
                update_data["caller_id"] = caller.id
            else:
                update_data["phone_number"] = None
                update_data["caller_id"] = None
        if caller_name is not None:
            update_data["caller_name"] = caller_name
        if not update_data:
            return call
        call = self.call_repo.update(call_id, **update_data)
        await event_bus.publish(
            Event(
                event_type=EventType.CALL_UPDATED,
                timestamp=datetime.utcnow(),
                data={
                    "call_id": call.id,
                    "phone_number": call.phone_number,
                    "caller_name": call.caller_name,
                    "status": call.status,
                },
                source="CallService",
            )
        )
        return call

    async def save_voicemail(
        self,
        audio_file: str,
        *,
        call_id: Optional[int] = None,
        phone_number: Optional[str] = None,
        caller_name: Optional[str] = None,
        duration: Optional[int] = None,
        transcription: Optional[str] = None,
    ) -> Voicemail:
        """
        Persiste un message vocal apres le bip (fichier deja ecrit sur disque).

        @param audio_file Chemin relatif ou absolu du WAV.
        @param call_id Appel associe (optionnel).
        @param phone_number Numero Caller ID.
        @param caller_name Nom Caller ID.
        @param duration Duree estimee en secondes.
        @param transcription Texte STT si deja disponible.
        @returns Ligne voicemails creee.
        """
        caller = None
        if phone_number:
            caller = self.caller_repo.get_by_phone_number(phone_number)
        vm = self.voicemail_repo.create_voicemail(
            audio_file=audio_file,
            phone_number=phone_number,
            caller_name=caller_name,
            caller_id=caller.id if caller else None,
            call_id=call_id,
            duration=duration,
            transcription=transcription,
        )
        await event_bus.publish(
            Event(
                event_type=EventType.VOICEMAIL_RECORDED,
                timestamp=datetime.utcnow(),
                data={
                    "voicemail_id": vm.id,
                    "call_id": call_id,
                    "phone_number": phone_number,
                    "audio_file": audio_file,
                    "duration": duration,
                    "transcription": transcription,
                },
                source="CallService",
            )
        )
        logger.info("Message vocal enregistre: id={} file={}", vm.id, audio_file)
        return vm

    async def set_voicemail_transcription(
        self, voicemail_id: int, transcription: str
    ) -> Optional[Voicemail]:
        """Met a jour la transcription STT d un message vocal."""
        text = (transcription or "").strip()
        if not text:
            return self.voicemail_repo.get_by_id(voicemail_id)
        return self.voicemail_repo.update(voicemail_id, transcription=text)

