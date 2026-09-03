"""
Cree ou reutilise un token API ProspectLab pour le worker VocalGuard OSINT.

A executer sur node15, depuis /opt/prospectlab (PYTHONPATH + config .env).
Ecrit uniquement le token sur stdout (une ligne).
"""

from __future__ import annotations

import sys

TOKEN_NAME = "VocalGuard-OSINT"


def main() -> int:
    """
    Garantit un token API lecture entreprises.

    @returns Code retour 0 si un token a ete imprime.
    """
    sys.path.insert(0, "/opt/prospectlab")
    from services.api_auth import APITokenManager

    manager = APITokenManager()
    existing = manager.list_tokens() or []
    for row in existing:
        name = (row.get("name") or "").strip()
        token = (row.get("token") or "").strip()
        if name == TOKEN_NAME and token and row.get("is_active", True):
            print(token)
            return 0
    created = manager.create_token(
        name=TOKEN_NAME,
        app_url="http://127.0.0.1:8110",
        can_read_entreprises=True,
        can_read_emails=False,
        can_read_statistics=False,
        can_read_campagnes=False,
        can_delete_entreprises=False,
    )
    print((created or {}).get("token") or "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
