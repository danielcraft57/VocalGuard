"""
Repositories SQLite Prospector (file, cache PL, sync).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from desktop.prospector.db.models import (
    AppSetting,
    CallSession,
    CallTranscriptLine,
    IncomingRingEvent,
    PlEntreprise,
    PlEntrepriseGroupe,
    PlGroupe,
    PlImportBatch,
    PlPhone,
    QueueItem,
    SyncOutbox,
)
from desktop.prospector.phone_utils import phone_digits
from desktop.prospector.prospectlab_client import ProspectLabClient


def _entreprise_fields(row: dict) -> dict[str, Any]:
    """Extrait champs affichage depuis payload API."""
    return {
        "prospectlab_id": int(row.get("id") or row.get("entreprise_id") or 0),
        "raison_sociale": str(row.get("raison_sociale") or row.get("nom") or row.get("name") or ""),
        "secteur": row.get("secteur"),
        "statut_pl": row.get("statut"),
        "ville": row.get("ville") or row.get("city"),
        "code_postal": row.get("code_postal") or row.get("postal_code"),
        "payload_json": json.dumps(row, ensure_ascii=False),
        "synced_at": datetime.utcnow(),
    }


class CampaignStore:
    """
    Acces persistence campagne / file / journal.

    @param session Session SQLAlchemy ouverte.
    @param pl_client Client API optionnel pour sync.
    """

    def __init__(self, session: Session, pl_client: Optional[ProspectLabClient] = None) -> None:
        self.session = session
        self.pl_client = pl_client

    def get_setting(self, key: str, default: str = "") -> str:
        """Lit app_setting."""
        row = self.session.get(AppSetting, key)
        return row.value if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Ecrit app_setting."""
        row = self.session.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key, value=value)
            self.session.add(row)
        else:
            row.value = value
        self.session.commit()

    def list_groupes_local(self) -> List[PlGroupe]:
        """Groupes en cache."""
        return list(self.session.scalars(select(PlGroupe).order_by(PlGroupe.nom)).all())

    def upsert_groupe_from_api(self, g: dict) -> PlGroupe:
        """
        Insere ou met a jour un groupe API.

        @param g Dict groupe ProspectLab.
        @returns Ligne pl_groupe.
        """
        pl_id = int(g.get("id") or 0)
        existing = self.session.scalar(select(PlGroupe).where(PlGroupe.prospectlab_id == pl_id))
        if existing is None:
            existing = PlGroupe(prospectlab_id=pl_id)
            self.session.add(existing)
        existing.nom = str(g.get("nom") or g.get("name") or f"Groupe {pl_id}")
        existing.description = g.get("description")
        existing.couleur = g.get("couleur") or g.get("color")
        existing.entreprises_count = int(g.get("entreprises_count") or g.get("count") or 0)
        existing.synced_at = datetime.utcnow()
        self.session.flush()
        return existing

    def refresh_groupes_from_api(self, client: Optional[ProspectLabClient] = None) -> int:
        """
        GET /groupes -> pl_groupe.

        @returns Nombre de groupes upsert.
        """
        api = client or self.pl_client
        if api is None:
            raise ValueError("Client ProspectLab requis.")
        count = 0
        for g in api.list_groupes():
            self.upsert_groupe_from_api(g)
            count += 1
        self.session.commit()
        return count

    def upsert_entreprise_from_api(self, row: dict, groupe: Optional[PlGroupe] = None) -> PlEntreprise:
        """
        Cache entreprise + telephones.

        @param row Payload entreprise API.
        @param groupe Groupe source optionnel.
        @returns PlEntreprise.
        """
        fields = _entreprise_fields(row)
        pl_id = fields["prospectlab_id"]
        if pl_id <= 0:
            raise ValueError("entreprise sans id")
        ent = self.session.scalar(select(PlEntreprise).where(PlEntreprise.prospectlab_id == pl_id))
        if ent is None:
            ent = PlEntreprise(prospectlab_id=pl_id)
            self.session.add(ent)
        for k, v in fields.items():
            if k != "prospectlab_id":
                setattr(ent, k, v)
        self.session.flush()

        tel = row.get("telephone") or row.get("display_phone") or row.get("phone")
        phones = row.get("phones") if isinstance(row.get("phones"), list) else []
        if tel and not phones:
            phones = [{"phone": tel, "is_primary": True}]
        seen_digits: set[str] = set()
        for p in phones:
            if not isinstance(p, dict):
                continue
            raw = str(p.get("phone") or p.get("number") or "")
            digits = phone_digits(raw)
            if not digits or digits in seen_digits:
                continue
            seen_digits.add(digits)
            existing_phone = self.session.scalar(
                select(PlPhone).where(
                    PlPhone.entreprise_id == ent.id,
                    PlPhone.phone_digits == digits,
                )
            )
            if existing_phone is None:
                existing_phone = PlPhone(
                    entreprise_id=ent.id,
                    phone_raw=raw,
                    phone_digits=digits,
                    is_primary=bool(p.get("is_primary") or p.get("primary")),
                    label=p.get("label"),
                )
                self.session.add(existing_phone)
            else:
                existing_phone.phone_raw = raw
                existing_phone.is_primary = bool(p.get("is_primary") or existing_phone.is_primary)
        if tel:
            digits = phone_digits(str(tel))
            if digits and digits not in seen_digits:
                self.session.add(
                    PlPhone(
                        entreprise_id=ent.id,
                        phone_raw=str(tel),
                        phone_digits=digits,
                        is_primary=True,
                    )
                )

        if groupe is not None:
            link = self.session.scalar(
                select(PlEntrepriseGroupe).where(
                    PlEntrepriseGroupe.entreprise_id == ent.id,
                    PlEntrepriseGroupe.groupe_id == groupe.id,
                )
            )
            if link is None:
                self.session.add(PlEntrepriseGroupe(entreprise_id=ent.id, groupe_id=groupe.id))
        self.session.flush()
        return ent

    def import_groupe_entreprises(
        self,
        groupe_pl_id: int,
        client: ProspectLabClient,
        *,
        clear_queue: bool = False,
        filters: Optional[dict[str, Any]] = None,
    ) -> PlImportBatch:
        """
        Import pagine /groupes/<id>/entreprises vers file locale.

        @param groupe_pl_id ID distant ProspectLab.
        @param client Client HTTP.
        @param clear_queue Supprime les queue_item todo avant import.
        @param filters Query API (has_phone, etc.).
        @returns Batch import.
        """
        filters = dict(filters or {})
        filters.setdefault("has_phone", 1)
        groupe = self.session.scalar(select(PlGroupe).where(PlGroupe.prospectlab_id == groupe_pl_id))
        if groupe is None:
            groupe = self.upsert_groupe_from_api(client.get_groupe(groupe_pl_id) or {"id": groupe_pl_id})

        batch = PlImportBatch(
            source_type="groupe",
            prospectlab_groupe_id=groupe_pl_id,
            filters_json=json.dumps(filters, ensure_ascii=False),
            started_at=datetime.utcnow(),
        )
        self.session.add(batch)
        self.session.flush()

        if clear_queue:
            for qi in self.session.scalars(select(QueueItem).where(QueueItem.local_status == "todo")).all():
                self.session.delete(qi)
            self.session.flush()

        count = 0
        for row in client.iter_groupe_entreprises(groupe_pl_id, **filters):
            ent = self.upsert_entreprise_from_api(row, groupe=groupe)
            exists = self.session.scalar(
                select(QueueItem).where(
                    QueueItem.entreprise_id == ent.id,
                    QueueItem.local_status.in_(("todo", "in_progress")),
                )
            )
            if exists is None:
                self.session.add(
                    QueueItem(
                        entreprise_id=ent.id,
                        import_batch_id=batch.id,
                        source_groupe_id=groupe.id,
                        local_status="todo",
                    )
                )
                count += 1
        batch.row_count = count
        batch.finished_at = datetime.utcnow()
        self.set_setting("last_selected_groupe_id", str(groupe_pl_id))
        self.session.commit()
        return batch

    def list_queue_items(
        self,
        *,
        status: Optional[str] = None,
        groupe_local_id: Optional[int] = None,
        limit: int = 500,
    ) -> List[QueueItem]:
        """Liste file avec entreprise chargee."""
        q = select(QueueItem).order_by(QueueItem.priority.desc(), QueueItem.id.asc()).limit(limit)
        if status:
            q = q.where(QueueItem.local_status == status)
        if groupe_local_id:
            q = q.where(QueueItem.source_groupe_id == groupe_local_id)
        return list(self.session.scalars(q).all())

    def next_queue_item(self) -> Optional[QueueItem]:
        """Prochain todo."""
        return self.session.scalar(
            select(QueueItem)
            .where(QueueItem.local_status == "todo")
            .order_by(QueueItem.priority.desc(), QueueItem.id.asc())
            .limit(1)
        )

    def set_queue_status(self, item_id: int, status: str) -> None:
        """Met a jour le statut local file."""
        item = self.session.get(QueueItem, item_id)
        if item:
            item.local_status = status
            item.last_outcome_at = datetime.utcnow()
            self.session.commit()

    def find_entreprise_by_phone(self, raw: Optional[str]) -> Optional[PlEntreprise]:
        """Match entrant sur phone_digits."""
        digits = phone_digits(raw)
        if not digits:
            return None
        phone_row = self.session.scalar(
            select(PlPhone).where(PlPhone.phone_digits == digits).limit(1)
        )
        if phone_row is None:
            if len(digits) >= 9:
                tail = digits[-9:]
                phone_row = self.session.scalar(
                    select(PlPhone).where(PlPhone.phone_digits.like(f"%{tail}")).limit(1)
                )
        if phone_row is None:
            return None
        return self.session.get(PlEntreprise, phone_row.entreprise_id)

    def dial_phone_for_entreprise(self, ent: PlEntreprise) -> Optional[str]:
        """Numero a composer (primary ou premier)."""
        phone = self.session.scalar(
            select(PlPhone)
            .where(PlPhone.entreprise_id == ent.id)
            .order_by(PlPhone.is_primary.desc(), PlPhone.id.asc())
            .limit(1)
        )
        return phone.phone_raw if phone else None

    def create_call_session(
        self,
        *,
        direction: str,
        phone_digits_val: Optional[str],
        entreprise_id: Optional[int] = None,
        queue_item_id: Optional[int] = None,
    ) -> CallSession:
        """Ouvre call_session."""
        cs = CallSession(
            direction=direction,
            phone_digits=phone_digits_val,
            entreprise_id=entreprise_id,
            queue_item_id=queue_item_id,
            started_at=datetime.utcnow(),
        )
        self.session.add(cs)
        self.session.commit()
        return cs

    def mark_session_hangup(self, session_id: int) -> None:
        """
        Horodate la fin d'appel au raccrochage (sans statut CRM).

        @param session_id Id call_session.
        """
        cs = self.session.get(CallSession, session_id)
        if cs is None:
            return
        if cs.ended_at is None:
            cs.ended_at = datetime.utcnow()
            self.session.commit()

    def set_session_wav_path(self, session_id: int, wav_path: Optional[str]) -> None:
        """
        Attache le chemin du fichier WAV enregistre pour une session d'appel.

        @param session Id ``call_session``.
        @param wav_path Chemin absolu ``.wav`` ou None pour effacer.
        """
        cs = self.session.get(CallSession, session_id)
        if cs is None:
            return
        cs.wav_session_dir = wav_path
        self.session.commit()

    def end_call_session(
        self,
        session_id: int,
        *,
        outcome: str,
        note: Optional[str] = None,
        wav_dir: Optional[str] = None,
        patch_pl: bool = False,
    ) -> CallSession:
        """Cloture session."""
        cs = self.session.get(CallSession, session_id)
        if cs is None:
            raise ValueError("session introuvable")
        cs.ended_at = datetime.utcnow()
        cs.outcome = outcome
        cs.note_text = note
        cs.wav_session_dir = wav_dir
        cs.prospectlab_patch_pending = patch_pl
        if cs.queue_item_id:
            qi = self.session.get(QueueItem, cs.queue_item_id)
            if qi:
                qi.local_status = "done" if outcome not in ("missed", "failed") else "todo"
                qi.last_outcome_at = datetime.utcnow()
        self.session.commit()
        return cs

    def add_transcript_line(
        self,
        session_id: int,
        *,
        speaker: str,
        text: str,
        is_final: bool = True,
    ) -> None:
        """Ajoute ligne STT."""
        line = CallTranscriptLine(
            call_session_id=session_id,
            speaker=speaker,
            text=text.strip(),
            is_final=is_final,
        )
        self.session.add(line)
        self.session.commit()

    def log_incoming_ring(
        self,
        *,
        caller_raw: Optional[str],
        matched_entreprise_id: Optional[int] = None,
        user_action: Optional[str] = None,
        call_session_id: Optional[int] = None,
    ) -> IncomingRingEvent:
        """Journal sonnerie."""
        ev = IncomingRingEvent(
            caller_id_raw=caller_raw,
            caller_id_digits=phone_digits(caller_raw),
            matched_entreprise_id=matched_entreprise_id,
            user_action=user_action,
            call_session_id=call_session_id,
        )
        self.session.add(ev)
        self.session.commit()
        return ev

    def list_incoming_events(self, limit: int = 100) -> List[IncomingRingEvent]:
        """Historique entrants."""
        return list(
            self.session.scalars(
                select(IncomingRingEvent).order_by(IncomingRingEvent.rang_at.desc()).limit(limit)
            ).all()
        )

    def list_call_sessions(self, limit: int = 100) -> List[CallSession]:
        """Journal appels."""
        return list(
            self.session.scalars(
                select(CallSession).order_by(CallSession.started_at.desc()).limit(limit)
            ).all()
        )

    def delete_call_session(
        self,
        session_id: int,
        *,
        delete_wav: bool = True,
    ) -> bool:
        """
        Supprime une session du journal (+ transcription, lien entrant).

        @param session_id Cle ``call_session``.
        @param delete_wav Efface le fichier WAV du disque si present.
        @returns False si session introuvable.
        """
        cs = self.session.get(CallSession, session_id)
        if cs is None:
            return False
        wav_path = (cs.wav_session_dir or "").strip()
        for line in self.session.scalars(
            select(CallTranscriptLine).where(CallTranscriptLine.call_session_id == session_id)
        ).all():
            self.session.delete(line)
        for ev in self.session.scalars(
            select(IncomingRingEvent).where(IncomingRingEvent.call_session_id == session_id)
        ).all():
            ev.call_session_id = None
        self.session.delete(cs)
        self.session.commit()
        if delete_wav and wav_path:
            try:
                p = Path(wav_path)
                if p.is_file():
                    p.unlink()
            except OSError:
                pass
        return True

    def clear_call_history(self, *, delete_wavs: bool = True) -> int:
        """
        Supprime toutes les sessions d'appel du journal local.

        @param delete_wavs Efface les WAV references.
        @returns Nombre de sessions supprimees.
        """
        ids = [cs.id for cs in self.list_call_sessions(limit=10_000)]
        count = 0
        for sid in ids:
            if self.delete_call_session(sid, delete_wav=delete_wavs):
                count += 1
        return count

    def entreprise_label(self, entreprise_id: Optional[int]) -> str:
        """
        Raison sociale pour l'historique.

        @param entreprise_id Cle locale pl_entreprise.
        @returns Libelle ou chaine vide.
        """
        if not entreprise_id:
            return ""
        ent = self.session.get(PlEntreprise, entreprise_id)
        return (ent.raison_sociale or "").strip() if ent else ""

    @staticmethod
    def call_duration_label(cs: CallSession) -> str:
        """
        Duree humaine d'une session.

        @param cs Ligne call_session.
        @returns Ex. ``03:42`` ou tiret si inconnue.
        """
        if cs.started_at and cs.ended_at:
            sec = max(0, int((cs.ended_at - cs.started_at).total_seconds()))
            m, s = divmod(sec, 60)
            return f"{m:02d}:{s:02d}"
        if cs.wav_session_dir:
            try:
                from desktop.prospector.call_player import wav_duration_seconds

                d = wav_duration_seconds(Path(cs.wav_session_dir))
                if d > 0:
                    m, s = divmod(int(d), 60)
                    return f"{m:02d}:{s:02d}"
            except Exception:
                pass
        return "—"

    def enqueue_sync_patch(
        self,
        path: str,
        body: dict,
        *,
        method: str = "PATCH",
    ) -> SyncOutbox:
        """Ajoute PATCH ProspectLab a la file offline."""
        row = SyncOutbox(method=method, path=path, body_json=json.dumps(body, ensure_ascii=False))
        self.session.add(row)
        self.session.commit()
        return row

    def flush_sync_outbox(self, client: Optional[ProspectLabClient] = None) -> int:
        """
        Envoie les PATCH en attente.

        @returns Nombre d'entrees envoyees.
        """
        api = client or self.pl_client
        if api is None:
            return 0
        sent = 0
        rows = list(
            self.session.scalars(
                select(SyncOutbox).where(SyncOutbox.sent_at.is_(None)).order_by(SyncOutbox.id.asc())
            ).all()
        )
        for row in rows:
            try:
                api._request(row.method, row.path, json=json.loads(row.body_json))
                row.sent_at = datetime.utcnow()
                sent += 1
            except Exception as exc:
                row.attempts += 1
                row.last_error = str(exc)[:2000]
        self.session.commit()
        return sent

    def close_call_and_sync_pl(
        self,
        session_id: int,
        *,
        statut: str,
        note: Optional[str] = None,
        client: Optional[ProspectLabClient] = None,
    ) -> None:
        """
        Cloture appel + PATCH statut ProspectLab (direct ou outbox).

        @param session_id ID call_session.
        @param statut Statut PL.
        @param note Note optionnelle.
        """
        cs = self.session.get(CallSession, session_id)
        if cs is None:
            return
        self.end_call_session(session_id, outcome=statut, note=note, patch_pl=True)
        if cs.entreprise_id is None:
            return
        ent = self.session.get(PlEntreprise, cs.entreprise_id)
        if ent is None:
            return
        path = f"/entreprises/{ent.prospectlab_id}/statut"
        body = {"statut": statut}
        if note:
            body["note"] = note
        api = client or self.pl_client
        if api is None:
            self.enqueue_sync_patch(path, body)
            return
        try:
            api.patch_entreprise_statut(ent.prospectlab_id, statut=statut, note=note)
        except Exception:
            self.enqueue_sync_patch(path, body)
