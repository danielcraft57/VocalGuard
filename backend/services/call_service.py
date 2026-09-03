"""
Service de gestion des appels.

Ce module cree, met a jour et journalise les appels dans la base
et publie les evenements associes. Il est egalement responsable
de declencher l'enrichissement OSINT des numeros via les
services adequats.
"""

from typing import Optional
from datetime import datetime
from pathlib import Path
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
        self.config = Config()
        self.phone_osint_service = PhoneOsintService(db, self.config)
    
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

    async def annotate_incoming_policy(
        self,
        call_id: int,
        *,
        profile: str,
        source: str,
        rings_before_answer: int = 0,
        ignored: bool = False,
    ) -> Optional[Call]:
        """
        Enregistre le profil policy sur l'appel (colonnes a plat) pour l'UI /calls.

        @param call_id ID appel.
        @param profile permitted | screened | blocked.
        @param source Source policy (ex. preset:voicemail).
        @param rings_before_answer Sonneries configurees.
        @param ignored True si policy ignore (fixe parallele).
        @returns Appel mis a jour ou None.
        """
        call = self.call_repo.get_by_id(call_id)
        if not call:
            return None
        return self.call_repo.update(
            call_id,
            incoming_profile=str(profile),
            incoming_policy_source=str(source),
            incoming_rings=int(rings_before_answer),
            incoming_ignored=bool(ignored),
        )

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
        
        if duration is not None:
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

    async def mark_call_no_message(
        self,
        call_id: int,
        *,
        reason: str = "vide",
    ) -> Optional[Call]:
        """
        Marque un appel sans message vocal (bips / silence seulement).

        Pas de STT : transcription fixe « Pas de message » + drapeau no_message.

        @param call_id ID appel.
        @param reason Cause (silence, bips_raccrochage, trop_court, ...).
        @returns Appel mis a jour ou None.
        """
        call = self.call_repo.get_by_id(call_id)
        if not call:
            return None
        # Plus besoin de garder un WAV d'accueil / bips sans message.
        audio_path = call.audio_file
        if audio_path:
            try:
                base = Path(self.config.base_path) if self.config.base_path else Path.cwd()
                wav = (base / str(audio_path).replace("\\", "/").lstrip("/")).resolve()
                wav.relative_to(base.resolve())
                if wav.is_file():
                    wav.unlink()
            except Exception:
                logger.debug("Suppression audio sans message ignoree ({})", audio_path)
        return self.call_repo.update(
            call_id,
            transcription="Pas de message",
            audio_file=None,
            no_message=True,
            no_message_reason=str(reason or "vide")[:80],
            transcription_cues=None,
        )

    async def set_transcription_and_intent(
        self,
        call_id: int,
        transcription: Optional[str] = None,
        intent_name: Optional[str] = None,
        cues: Optional[list] = None,
    ) -> Optional[Call]:
        """
        Met a jour la transcription et/ou l'intent IVR associe a un appel.

        - transcription est stockee dans Call.transcription
        - intent_name est stocke dans Call.ivr_intent
        - cues SRT (4-5 mots) dans Call.transcription_cues (JSONB)
        """
        call = self.call_repo.get_by_id(call_id)
        if not call:
            return None

        update_data: dict = {}
        if transcription is not None:
            update_data["transcription"] = transcription

        if intent_name:
            update_data["ivr_intent"] = str(intent_name)[:100]

        if cues:
            update_data["transcription_cues"] = cues

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
        """
        Met a jour la transcription STT d un message vocal.

        @param voicemail_id Identifiant du message.
        @param transcription Texte reconnu.
        @returns Message mis a jour ou None si introuvable.
        """
        text = (transcription or "").strip()
        if not text:
            return self.voicemail_repo.get_by_id(voicemail_id)
        vm = self.voicemail_repo.update(voicemail_id, transcription=text)
        if vm is None:
            return None
        await event_bus.publish(
            Event(
                event_type=EventType.VOICEMAIL_TRANSCRIBED,
                timestamp=datetime.utcnow(),
                data={
                    "voicemail_id": vm.id,
                    "call_id": vm.call_id,
                    "phone_number": vm.phone_number,
                    "caller_name": vm.caller_name,
                    "transcription": text,
                    "duration": vm.duration,
                },
                source="CallService",
            )
        )
        return vm

