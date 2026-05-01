"""Routes API classiques pour gérer les tokens de l'API publique."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from backend.api.models import PublicApiTokenCreate, PublicApiTokenResponse, PublicApiTokenUpdate
from backend.core.config import Config
from backend.database.database import get_db
from backend.database.models import ApiPublicToken

router = APIRouter(prefix="/tokens", tags=["tokens"])


def _token_preview(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "***"
    return (s[:10] + "…") if len(s) > 10 else s


def _to_token_response(row: ApiPublicToken, include_token: bool) -> PublicApiTokenResponse:
    return PublicApiTokenResponse(
        id=row.id,
        name=row.name,
        app_url=getattr(row, "app_url", None),
        token=row.token if include_token else None,
        token_preview=_token_preview(row.token),
        is_active=bool(row.is_active),
        can_read_agenda=bool(row.can_read_agenda),
        can_write_agenda=bool(row.can_write_agenda),
        can_write_entreprises=bool(row.can_write_entreprises),
        can_manage_tokens=bool(row.can_manage_tokens),
        can_read_customers=bool(getattr(row, "can_read_customers", False)),
        can_write_customers=bool(getattr(row, "can_write_customers", False)),
        can_read_quotes=bool(getattr(row, "can_read_quotes", False)),
        can_write_quotes=bool(getattr(row, "can_write_quotes", False)),
        can_read_calls=bool(getattr(row, "can_read_calls", False)),
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )


def _require_token_admin(
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
) -> None:
    """
    Protection simple pour l'admin tokens:
    - si API_PUBLIC_ADMIN_TOKEN est défini, il doit matcher le header x-admin-token
    - sinon, en dev local, on laisse passer (utile pour itérer).
    """
    config = Config()
    expected = (config.api_public_admin_token or "").strip()
    if not expected:
        return
    if not x_admin_token or x_admin_token.strip() != expected:
        raise HTTPException(status_code=401, detail="Accès admin tokens requis.")


@router.get("/docs")
async def tokens_docs() -> dict:
    """
    Documentation des endpoints publics (agenda, entreprises, clients, devis, appels).
    """
    return {
        "name": "VocalGuard Public API",
        "base_url": "/api/v1/public",
        "auth": {
            "headers": ["Authorization: Bearer <token>", "x-api-token: <token>"],
            "notes": [
                "Le token doit être actif.",
                "Chaque endpoint vérifie aussi une permission (can_read_*, can_write_*).",
                "Note: les permissions can_read_customers/can_write_customers correspondent aux endpoints /public/clients (nom legacy conservé en base).",
            ],
        },
        "tokens_admin_base_url": "/api/v1/tokens",
        "how_to": {
            "send": "Envoyez vos données en JSON, avec le token en header.",
            "receive": "En succès, l'API renvoie un JSON. En erreur, status HTTP + champ detail.",
        },
        "endpoints": [
            {
                "method": "GET",
                "path": "/public/agenda",
                "permission": "can_read_agenda",
                "title": "Lister les rendez-vous agenda",
                "description": "Retourne la liste des rendez-vous triés par date de début.",
                "request": {"headers": ["Authorization: Bearer <token>"], "query": {}, "body": None},
                "responses": {
                    "200": {
                        "example": [
                            {
                                "id": 42,
                                "client_id": 10,
                                "entreprise_id": 7,
                                "title": "RDV découverte",
                                "start_time": "2026-05-06T11:00:00",
                                "end_time": "2026-05-06T12:00:00",
                                "status": "scheduled",
                            }
                        ]
                    },
                    "401": {"example": {"detail": "Token API public requis."}},
                    "403": {"example": {"detail": "Ce token ne peut pas lire l'agenda."}},
                },
            },
            {
                "method": "POST",
                "path": "/public/agenda",
                "permission": "can_write_agenda",
                "title": "Créer un rendez-vous agenda",
                "description": "Crée un rendez-vous manuel. Vérifie conflit et horaires ouvrés.",
                "request": {
                    "headers": ["Authorization: Bearer <token>"],
                    "query": {},
                    "body": {
                        "client_id": 10,
                        "entreprise_id": 7,
                        "phone_number": "03 87 78 09 16",
                        "title": "RDV site vitrine",
                        "start_time": "2026-05-06T11:00:00",
                        "end_time": "2026-05-06T12:00:00",
                        "notes": "Premier échange",
                    },
                },
                "responses": {
                    "201": {"example": {"id": 43, "title": "RDV site vitrine", "status": "scheduled"}},
                    "400": {"example": {"detail": "Le rendez-vous est hors plage horaire de travail."}},
                    "409": {"example": {"detail": "Conflit detecte avec un autre rendez-vous."}},
                },
            },
            {
                "method": "PATCH",
                "path": "/public/agenda/{appointment_id}",
                "permission": "can_write_agenda",
                "title": "Modifier un rendez-vous",
                "description": "Met à jour partiellement un rendez-vous existant.",
                "request": {
                    "headers": ["Authorization: Bearer <token>"],
                    "query": {},
                    "body": {"title": "RDV confirmé", "status": "scheduled"},
                },
                "responses": {
                    "200": {"example": {"id": 43, "title": "RDV confirmé", "status": "scheduled"}},
                    "404": {"example": {"detail": "Rendez-vous introuvable."}},
                },
            },
            {
                "method": "DELETE",
                "path": "/public/agenda/{appointment_id}",
                "permission": "can_write_agenda",
                "title": "Supprimer un rendez-vous",
                "description": "Supprime un rendez-vous agenda.",
                "request": {"headers": ["Authorization: Bearer <token>"], "query": {}, "body": None},
                "responses": {
                    "204": {"example": None},
                    "404": {"example": {"detail": "Rendez-vous introuvable."}},
                },
            },
            {
                "method": "POST",
                "path": "/public/agenda/booking",
                "permission": "can_write_agenda",
                "title": "Booking public depuis formulaire",
                "description": "Crée un RDV de 1h et upsert l'entreprise (emails M2M, phone, website...).",
                "request": {
                    "headers": ["Authorization: Bearer <token>"],
                    "query": {},
                    "body": {
                        "preferred_date": "2026-05-06",
                        "preferred_time": "11:00",
                        "service": "site_vitrine",
                        "budget": "1500",
                        "project_type": "web",
                        "name": "Alex Martin",
                        "company_name": "Acme Studio",
                        "email": "contact@example.com",
                        "emails": ["contact@example.com", "sales@example.com"],
                        "phone": "+33 1 23 45 67 89",
                        "website": "https://example.com",
                        "message": "Demande issue du formulaire public",
                    },
                },
                "responses": {
                    "201": {
                        "example": {
                            "id": 44,
                            "title": "RDV site - Alex Martin - site_vitrine",
                            "start_time": "2026-05-06T11:00:00",
                            "end_time": "2026-05-06T12:00:00",
                        }
                    },
                    "409": {"example": {"detail": "Conflit detecte avec un autre rendez-vous."}},
                },
            },
            {
                "method": "GET",
                "path": "/public/availability/work-days",
                "permission": "can_read_agenda",
                "title": "Lire les jours ouvrés",
                "description": "Retourne les jours activés dans la configuration agenda.",
                "request": {"headers": ["Authorization: Bearer <token>"], "query": {}, "body": None},
                "responses": {"200": {"example": {"monday": True, "saturday": False}}},
            },
            {
                "method": "GET",
                "path": "/public/availability/slots",
                "permission": "can_read_agenda",
                "title": "Lister les créneaux disponibles",
                "description": "Retourne les créneaux libres dans une plage de dates.",
                "request": {
                    "headers": ["Authorization: Bearer <token>"],
                    "query": {"from_date": "2026-05-01", "to_date": "2026-05-15"},
                    "body": None,
                },
                "responses": {
                    "200": {
                        "example": {
                            "count": 2,
                            "slots": [
                                {"date": "2026-05-06", "start_time": "11:00", "end_time": "12:00"},
                                {"date": "2026-05-06", "start_time": "14:00", "end_time": "15:00"},
                            ],
                        }
                    }
                },
            },
            {
                "method": "POST",
                "path": "/public/entreprises",
                "permission": "can_write_entreprises",
                "title": "Créer une entreprise",
                "description": "Crée une entreprise avec emails normalisés (M2M).",
                "request": {
                    "headers": ["Authorization: Bearer <token>"],
                    "query": {},
                    "body": {
                        "name": "Acme Studio",
                        "phone_number": "+33 1 23 45 67 89",
                        "website": "https://example.com",
                        "city": "Metz",
                        "country": "France",
                        "emails": ["contact@example.com", "hello@example.com"],
                    },
                },
                "responses": {
                    "201": {"example": {"id": 7, "name": "Acme Studio", "emails": ["contact@example.com"]}},
                    "400": {"example": {"detail": "Payload invalide"}},
                },
            },
            {
                "method": "PATCH",
                "path": "/public/entreprises/{entreprise_id}",
                "permission": "can_write_entreprises",
                "title": "Modifier une entreprise",
                "description": "Met à jour les champs d'une entreprise et ses emails.",
                "request": {
                    "headers": ["Authorization: Bearer <token>"],
                    "query": {},
                    "body": {"city": "Nancy", "emails": ["contact@example.com"]},
                },
                "responses": {
                    "200": {"example": {"id": 7, "city": "Nancy", "emails": ["contact@example.com"]}},
                    "404": {"example": {"detail": "Entreprise introuvable."}},
                },
            },
            {
                "method": "GET",
                "path": "/public/clients",
                "permission": "can_read_customers",
                "title": "Lister les clients (contacts)",
                "description": "Retourne les contacts clients.",
                "request": {"headers": ["Authorization: Bearer <token>"], "query": {}, "body": None},
                "responses": {
                    "200": {
                        "example": [
                            {
                                "id": 10,
                                "entreprise_id": 7,
                                "name": "Alex Martin",
                                "email": "alex.martin@example.com",
                                "phone_number": "+33 1 23 45 67 89",
                            }
                        ]
                    }
                },
            },
            {
                "method": "POST",
                "path": "/public/clients",
                "permission": "can_write_customers",
                "title": "Créer un client (contact)",
                "description": "Crée un contact client, lié optionnellement à une entreprise.",
                "request": {
                    "headers": ["Authorization: Bearer <token>"],
                    "query": {},
                    "body": {
                        "entreprise_id": 7,
                        "name": "Alex Martin",
                        "email": "alex.martin@example.com",
                        "phone_number": "+33 1 23 45 67 89",
                        "notes": "Contact principal",
                    },
                },
                "responses": {"201": {"example": {"id": 11, "entreprise_id": 7, "name": "Alex Martin"}}},
            },
            {
                "method": "GET",
                "path": "/public/quotes",
                "permission": "can_read_quotes",
                "title": "Lister les devis",
                "description": "Retourne la liste des devis.",
                "request": {"headers": ["Authorization: Bearer <token>"], "query": {}, "body": None},
                "responses": {
                    "200": {
                        "example": [
                            {
                                "id": 3,
                                "client_id": 11,
                                "title": "Site vitrine",
                                "status": "draft",
                                "total_ht": 150000,
                                "total_ttc": 150000,
                            }
                        ]
                    }
                },
            },
            {
                "method": "POST",
                "path": "/public/quotes",
                "permission": "can_write_quotes",
                "title": "Créer un devis",
                "description": "Crée un devis et calcule les totaux.",
                "request": {
                    "headers": ["Authorization: Bearer <token>"],
                    "query": {},
                    "body": {
                        "client_id": 11,
                        "phone_number": "+33 1 23 45 67 89",
                        "title": "Pack identité",
                        "lines": [{"description": "Création site", "quantity": 1, "unit_price": 1500}],
                        "notes": "Priorité haute",
                        "status": "draft",
                    },
                },
                "responses": {"201": {"example": {"id": 4, "title": "Pack identité", "total_ht": 150000}}},
            },
            {
                "method": "GET",
                "path": "/public/calls",
                "permission": "can_read_calls",
                "title": "Lister les appels",
                "description": "Retourne les appels (pagination skip/limit).",
                "request": {
                    "headers": ["Authorization: Bearer <token>"],
                    "query": {"skip": 0, "limit": 100},
                    "body": None,
                },
                "responses": {
                    "200": {
                        "example": {
                            "total": 120,
                            "skip": 0,
                            "limit": 100,
                            "calls": [
                                {
                                    "id": 900,
                                    "phone_number": "0387780916",
                                    "caller_name": "Inconnu",
                                    "call_time": "2026-05-01T09:31:00",
                                    "status": "completed",
                                    "duration": 52,
                                }
                            ],
                        }
                    }
                },
            },
        ],
    }


@router.get("", response_model=List[PublicApiTokenResponse], dependencies=[Depends(_require_token_admin)])
@router.get("/", response_model=List[PublicApiTokenResponse], dependencies=[Depends(_require_token_admin)])
async def list_tokens(db: Session = Depends(get_db)) -> List[PublicApiTokenResponse]:
    rows = db.query(ApiPublicToken).order_by(ApiPublicToken.created_at.desc()).all()
    return [_to_token_response(x, include_token=False) for x in rows]


@router.post("", response_model=PublicApiTokenResponse, status_code=201, dependencies=[Depends(_require_token_admin)])
@router.post("/", response_model=PublicApiTokenResponse, status_code=201, dependencies=[Depends(_require_token_admin)])
async def create_token(payload: PublicApiTokenCreate, db: Session = Depends(get_db)) -> PublicApiTokenResponse:
    url = (payload.app_url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Le champ app_url est requis.")
    name = (payload.name or "").strip() or None
    if not name:
        now = datetime.utcnow().strftime("%d/%m/%Y %H:%M")
        name = f"{url.replace('https://', '').replace('http://', '').replace('www.', '').strip()} - {now}"
    token = ApiPublicToken(
        name=name,
        app_url=url,
        token=secrets.token_hex(32),
        is_active=True,
        can_read_agenda=payload.can_read_agenda,
        can_write_agenda=payload.can_write_agenda,
        can_write_entreprises=payload.can_write_entreprises,
        can_manage_tokens=payload.can_manage_tokens,
        # nouveaux droits éventuels (si colonnes absentes, ignorées côté DB sqlite ancienne)
        can_read_customers=getattr(payload, "can_read_customers", False),
        can_write_customers=getattr(payload, "can_write_customers", False),
        can_read_quotes=getattr(payload, "can_read_quotes", False),
        can_write_quotes=getattr(payload, "can_write_quotes", False),
        can_read_calls=getattr(payload, "can_read_calls", False),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return _to_token_response(token, include_token=True)


@router.get("/{token_id}/reveal", response_model=PublicApiTokenResponse, dependencies=[Depends(_require_token_admin)])
async def reveal_token(token_id: int, db: Session = Depends(get_db)) -> PublicApiTokenResponse:
    row = db.get(ApiPublicToken, token_id)  # type: ignore[arg-type]
    if not row:
        raise HTTPException(status_code=404, detail="Token introuvable.")
    return _to_token_response(row, include_token=True)


@router.patch("/{token_id}", response_model=PublicApiTokenResponse, dependencies=[Depends(_require_token_admin)])
async def patch_token(token_id: int, payload: PublicApiTokenUpdate, db: Session = Depends(get_db)) -> PublicApiTokenResponse:
    row = db.get(ApiPublicToken, token_id)  # type: ignore[arg-type]
    if not row:
        raise HTTPException(status_code=404, detail="Token introuvable.")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _to_token_response(row, include_token=False)


@router.post("/{token_id}/revoke", status_code=204, dependencies=[Depends(_require_token_admin)])
async def revoke_token(token_id: int, db: Session = Depends(get_db)) -> Response:
    row = db.get(ApiPublicToken, token_id)  # type: ignore[arg-type]
    if not row:
        raise HTTPException(status_code=404, detail="Token introuvable.")
    row.is_active = False
    db.commit()
    return Response(status_code=204)


@router.delete("/{token_id}", status_code=204, dependencies=[Depends(_require_token_admin)])
async def delete_token(token_id: int, db: Session = Depends(get_db)) -> Response:
    row = db.get(ApiPublicToken, token_id)  # type: ignore[arg-type]
    if not row:
        raise HTTPException(status_code=404, detail="Token introuvable.")
    db.delete(row)
    db.commit()
    return Response(status_code=204)

