"""
Collecte legere de slots (nom, telephone, email, creneau RDV) pendant un appel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from loguru import logger
from sqlalchemy.orm import Session

from backend.database.models import CallLead

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"(?:\+33|0)\s*[1-9](?:[\s.\-]?\d{2}){4}",
)


@dataclass
class SlotSession:
    """
    Etat de collecte pour un intent (coords / email / rdv).

    @param intent_tag Intent qui a declenche la collecte.
    @param pending_slots Slots encore a demander.
    @param values Valeurs deja capturees.
    """

    intent_tag: str
    pending_slots: List[str] = field(default_factory=list)
    values: Dict[str, str] = field(default_factory=dict)

    @property
    def done(self) -> bool:
        """True si tous les slots sont remplis."""
        return not self.pending_slots

    def current_prompt(self) -> str:
        """
        Phrase a jouer pour le prochain slot.

        @returns Texte TTS.
        """
        if not self.pending_slots:
            return "Merci, j'ai bien note vos informations."
        slot = self.pending_slots[0]
        prompts = {
            "nom": "Quel est votre nom ?",
            "telephone": "Quel est votre numero de telephone ?",
            "email": "Quelle est votre adresse email ?",
            "creneau": "Quel jour ou creneau vous arrangerait ?",
        }
        return prompts.get(slot, "Pouvez-vous preciser ?")


def slots_for_action(action: Optional[str], intent_tag: Optional[str] = None) -> List[str]:
    """
    Liste ordonnee des slots a collecter selon l'action intent.

    @param action Champ action BDD.
    @param intent_tag Tag de secours.
    @returns Liste de noms de slots.
    """
    act = (action or "").strip()
    tag = (intent_tag or "").strip()
    if act == "collect_coords" or tag == "prendre_coordonnees":
        return ["nom", "telephone", "email"]
    if act == "collect_email" or tag == "contact_email":
        return ["email"]
    if act == "collect_rdv_slot" or tag == "prise_rdv":
        return ["creneau", "nom", "telephone"]
    return []


def start_slot_session(action: Optional[str], intent_tag: str) -> Optional[SlotSession]:
    """
    Demarre une session de slots si l'intent le demande.

    @param action Action runtime.
    @param intent_tag Tag committe.
    @returns Session ou None.
    """
    pending = slots_for_action(action, intent_tag)
    if not pending:
        return None
    return SlotSession(intent_tag=intent_tag, pending_slots=list(pending))


def extract_slot_value(slot: str, text: str) -> Optional[str]:
    """
    Extrait une valeur depuis une utterance STT.

    @param slot Nom du slot.
    @param text Texte transcrit.
    @returns Valeur ou None si rien d'exploitable.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if slot == "email":
        m = _EMAIL_RE.search(raw.replace(" arobase ", "@").replace(" at ", "@"))
        if m:
            return m.group(0).lower()
        # STT oral grossier : garder le texte si contient "point" / mail-like
        if "@" in raw or "mail" in raw.lower():
            return raw
        return raw if len(raw) >= 5 else None
    if slot == "telephone":
        m = _PHONE_RE.search(raw)
        if m:
            digits = re.sub(r"\D", "", m.group(0))
            if digits.startswith("33") and len(digits) >= 11:
                digits = "0" + digits[2:]
            return digits
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 10:
            return digits[-10:] if len(digits) > 10 else digits
        return raw if any(ch.isdigit() for ch in raw) else None
    if slot in ("nom", "creneau"):
        cleaned = re.sub(
            r"(?i)^(je m[' ]appelle|mon nom (c[' ]est|est)|je suis)\s+",
            "",
            raw,
        ).strip(" .,")
        return cleaned if len(cleaned) >= 2 else None
    return raw


def feed_slot_utterance(session: SlotSession, text: str) -> bool:
    """
    Ingere une phrase pour le slot courant.

    @param session Session active.
    @param text Texte STT du tour.
    @returns True si un slot a ete rempli.
    """
    if not session.pending_slots:
        return False
    slot = session.pending_slots[0]
    value = extract_slot_value(slot, text)
    if not value:
        return False
    session.values[slot] = value
    session.pending_slots.pop(0)
    logger.info("Slot {} = {!r} (reste {})", slot, value, session.pending_slots)
    return True


def persist_call_lead(
    db: Session,
    session: SlotSession,
    *,
    call_id: Optional[int] = None,
    phone_number: Optional[str] = None,
) -> CallLead:
    """
    Enregistre le lead en base.

    @param db Session SQLAlchemy.
    @param session Slots collectes.
    @param call_id ID appel.
    @param phone_number Numero appelant.
    @returns Ligne CallLead.
    """
    notes_parts: List[str] = []
    if session.values.get("creneau"):
        notes_parts.append(f"creneau={session.values['creneau']}")
    lead = CallLead(
        call_id=call_id,
        phone_number=phone_number,
        name=session.values.get("nom"),
        email=session.values.get("email"),
        callback_phone=session.values.get("telephone"),
        notes="; ".join(notes_parts) if notes_parts else None,
        intent_tag=session.intent_tag,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def confirmation_text(session: SlotSession) -> str:
    """
    Phrase de confirmation vocale apres collecte.

    @param session Session terminee.
    @returns Texte a jouer.
    """
    bits: List[str] = []
    if session.values.get("nom"):
        bits.append(f"nom {session.values['nom']}")
    if session.values.get("telephone"):
        bits.append(f"telephone {session.values['telephone']}")
    if session.values.get("email"):
        bits.append(f"email {session.values['email']}")
    if session.values.get("creneau"):
        bits.append(f"creneau {session.values['creneau']}")
    if not bits:
        return "Merci, vos informations sont enregistrees."
    return "Merci. J'ai note : " + ", ".join(bits) + "."
