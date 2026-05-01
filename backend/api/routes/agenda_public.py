"""API publique agenda: liens email de confirmation/annulation/suppression."""

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.core.config import Config
from backend.database.database import get_db
from backend.database.models import Appointment
from backend.services.email_service import send_html_email

router = APIRouter()


class SendAgendaEmailRequest(BaseModel):
    email: EmailStr
    recipient_name: str | None = None
    expires_hours: int = Field(default=72, ge=1, le=240)


def _encode_token(secret: str, payload: dict) -> str:
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return f"{payload_b64}.{sig_b64}"


def _decode_token(secret: str, token: str) -> dict:
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Token invalide.") from exc
    expected = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    expected_b64 = base64.urlsafe_b64encode(expected).decode("utf-8").rstrip("=")
    if not hmac.compare_digest(expected_b64, sig_b64):
        raise HTTPException(status_code=401, detail="Signature invalide.")
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Token expiré.")
    return payload


def _build_email_html(title: str, start_time: datetime, links: dict[str, str]) -> tuple[str, str]:
    date_label = start_time.astimezone().strftime("%d/%m/%Y à %H:%M")
    text_body = (
        f"Rendez-vous: {title}\n"
        f"Date: {date_label}\n\n"
        f"Confirmer: {links['confirm']}\n"
        f"Annuler: {links['cancel']}\n"
        f"Supprimer: {links['delete']}\n"
    )
    html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:680px;margin:auto;background:#0f172a;color:#e2e8f0;border-radius:14px;padding:24px;border:1px solid #1e293b;">
      <h2 style="margin:0 0 10px;color:#38bdf8;">DanielCraft - Confirmation de rendez-vous</h2>
      <p style="margin:0 0 8px;">Votre rendez-vous <strong>{title}</strong> est prévu le <strong>{date_label}</strong>.</p>
      <p style="margin:0 0 14px;opacity:.9;">Choisissez l'action souhaitée :</p>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 18px;">
        <a href="{links['confirm']}" style="background:#16a34a;color:white;text-decoration:none;padding:10px 14px;border-radius:8px;font-weight:600;">Valider</a>
        <a href="{links['cancel']}" style="background:#f59e0b;color:white;text-decoration:none;padding:10px 14px;border-radius:8px;font-weight:600;">Annuler</a>
        <a href="{links['delete']}" style="background:#dc2626;color:white;text-decoration:none;padding:10px 14px;border-radius:8px;font-weight:600;">Supprimer</a>
      </div>
      <p style="opacity:.78;font-size:13px;margin:0;">Liens sécurisés et limités dans le temps.</p>
    </div>
    """
    return html, text_body


def _render_action_page(title: str, status: str, message: str) -> str:
    color = {"ok": "#16a34a", "warn": "#f59e0b", "danger": "#dc2626"}.get(status, "#0284c7")
    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>DanielCraft - Agenda</title>
      </head>
      <body style="margin:0;background:#0b1220;color:#e2e8f0;font-family:Segoe UI,Arial,sans-serif;">
        <div style="max-width:680px;margin:40px auto;padding:22px;border-radius:14px;background:#111827;border:1px solid #1f2937;">
          <h2 style="margin:0 0 10px;color:#38bdf8;">DanielCraft - Gestion de rendez-vous</h2>
          <h3 style="margin:0 0 12px;color:{color};">{title}</h3>
          <p style="margin:0;line-height:1.5;">{message}</p>
        </div>
      </body>
    </html>
    """


@router.post("/agenda/public/{appointment_id}/send-email")
async def send_agenda_public_email(
    appointment_id: int,
    payload: SendAgendaEmailRequest,
    db: Session = Depends(get_db),
) -> dict:
    config = Config()
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Rendez-vous introuvable.")

    expires_at = datetime.now(timezone.utc) + timedelta(hours=payload.expires_hours)
    links: dict[str, str] = {}
    for action in ("confirm", "cancel", "delete"):
        token = _encode_token(
            config.agenda_public_secret,
            {"aid": appointment.id, "action": action, "exp": int(expires_at.timestamp())},
        )
        links[action] = f"{config.public_base_url.rstrip('/')}/api/v1/agenda/public/action?action={action}&token={token}"

    html_body, text_body = _build_email_html(appointment.title, appointment.start_time, links)
    send_html_email(
        config=config,
        to_email=payload.email,
        subject=f"Gestion de votre rendez-vous - {appointment.title}",
        html_body=html_body,
        text_body=text_body,
    )
    return {"ok": True, "appointment_id": appointment_id, "email": payload.email}


@router.get("/agenda/public/action", response_class=HTMLResponse)
async def agenda_public_action(
    action: str = Query(..., pattern="^(confirm|cancel|delete)$"),
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    config = Config()
    data = _decode_token(config.agenda_public_secret, token)
    if data.get("action") != action:
        raise HTTPException(status_code=400, detail="Action incohérente.")
    appointment_id = int(data["aid"])
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Rendez-vous introuvable.")

    if action == "confirm":
        appointment.status = "confirmed"
        db.commit()
        return HTMLResponse(
            _render_action_page("Rendez-vous validé", "ok", "Votre rendez-vous a bien été confirmé.")
        )
    if action == "cancel":
        appointment.status = "cancelled"
        db.commit()
        return HTMLResponse(
            _render_action_page("Rendez-vous annulé", "warn", "Votre rendez-vous a été annulé.")
        )
    db.delete(appointment)
    db.commit()
    return HTMLResponse(
        _render_action_page("Rendez-vous supprimé", "danger", "Votre rendez-vous a été supprimé définitivement.")
    )

