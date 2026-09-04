"""
Persistance des sessions tchatche KB.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.database.models import KbChatSession


def _as_list(value: Any) -> List[Any]:
    """Force une liste JSON."""
    return value if isinstance(value, list) else []


def session_to_dict(row: KbChatSession) -> Dict[str, Any]:
    """
    Serialise une session ORM.

    @param row Ligne DB.
    @returns Dict API (camelCase UI-friendly + snake).
    """
    return {
        "id": row.id,
        "title": row.title or "Conversation",
        "messages": _as_list(row.messages),
        "recentReplies": _as_list(row.recent_replies),
        "recentTags": _as_list(row.recent_tags),
        "recentUserTexts": _as_list(row.recent_user_texts),
        "createdAt": row.created_at.isoformat() + "Z" if row.created_at else None,
        "updatedAt": row.updated_at.isoformat() + "Z" if row.updated_at else None,
    }


def list_sessions(db: Session, *, limit: int = 30) -> List[Dict[str, Any]]:
    """
    Liste les sessions (plus recentes en tete).

    @param db Session SQLAlchemy.
    @param limit Cap.
    @returns Liste de dicts.
    """
    rows = (
        db.query(KbChatSession)
        .order_by(KbChatSession.updated_at.desc())
        .limit(max(1, min(100, int(limit))))
        .all()
    )
    return [session_to_dict(r) for r in rows]


def get_session(db: Session, session_id: str) -> Optional[Dict[str, Any]]:
    """
    Charge une session par id.

    @param db Session.
    @param session_id Id client.
    @returns Dict ou None.
    """
    row = db.query(KbChatSession).filter(KbChatSession.id == session_id).one_or_none()
    return session_to_dict(row) if row else None


def upsert_session(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cree ou met a jour une session complete.

    @param db Session.
    @param payload Corps API (id, title, messages, recent*).
    @returns Dict sauve.
    @raises ValueError Si id manquant.
    """
    sid = str(payload.get("id") or "").strip()
    if not sid or len(sid) > 80:
        raise ValueError("id de session invalide")

    title = str(payload.get("title") or "Conversation").strip()[:255] or "Conversation"
    messages = _as_list(payload.get("messages"))
    recent_replies = _as_list(
        payload.get("recentReplies")
        if "recentReplies" in payload
        else payload.get("recent_replies")
    )
    recent_tags = _as_list(
        payload.get("recentTags") if "recentTags" in payload else payload.get("recent_tags")
    )
    recent_user_texts = _as_list(
        payload.get("recentUserTexts")
        if "recentUserTexts" in payload
        else payload.get("recent_user_texts")
    )

    row = db.query(KbChatSession).filter(KbChatSession.id == sid).one_or_none()
    now = datetime.utcnow()
    if row is None:
        row = KbChatSession(
            id=sid,
            title=title,
            messages=messages,
            recent_replies=recent_replies,
            recent_tags=recent_tags,
            recent_user_texts=recent_user_texts,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.title = title
        row.messages = messages
        row.recent_replies = recent_replies
        row.recent_tags = recent_tags
        row.recent_user_texts = recent_user_texts
        row.updated_at = now

    db.commit()
    db.refresh(row)
    return session_to_dict(row)


def delete_session(db: Session, session_id: str) -> bool:
    """
    Supprime une session.

    @returns True si supprimee.
    """
    row = db.query(KbChatSession).filter(KbChatSession.id == session_id).one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def import_sessions(db: Session, sessions: List[Dict[str, Any]]) -> int:
    """
    Importe un lot (ex. migration localStorage) sans ecraser plus recent.

    @param db Session.
    @param sessions Liste de payloads.
    @returns Nombre upsertes.
    """
    n = 0
    for item in sessions:
        sid = str(item.get("id") or "").strip()
        if not sid:
            continue
        existing = db.query(KbChatSession).filter(KbChatSession.id == sid).one_or_none()
        if existing is not None:
            # Garde la version DB si deja plus recente
            incoming = str(item.get("updatedAt") or item.get("updated_at") or "")
            if existing.updated_at and incoming:
                try:
                    # Compare ISO basique
                    if incoming.replace("Z", "") <= existing.updated_at.isoformat():
                        continue
                except Exception:
                    pass
        upsert_session(db, item)
        n += 1
    return n
