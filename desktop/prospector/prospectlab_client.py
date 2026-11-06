"""
Client HTTP ProspectLab /api/public.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

import httpx

from desktop.prospector.settings import prospectlab_api_prefix, prospectlab_token


class ProspectLabError(Exception):
    """Erreur API ProspectLab."""


class ProspectLabClient:
    """
    Client REST Bearer pour /api/public.

    @param base_url Prefixe complet .../api/public (optionnel).
    @param token Bearer token.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or prospectlab_api_prefix()).rstrip("/")
        self.token = (token or prospectlab_token()).strip()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise ProspectLabError("Token ProspectLab manquant (PROSPECTLAB_TOKEN).")
        return {"Authorization": f"Bearer {self.token}"}

    def _url(self, path: str) -> str:
        if not self.base_url:
            raise ProspectLabError("URL ProspectLab manquante (PROSPECTLAB_URL).")
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """
        Execute une requete HTTP.

        @param method GET, PATCH, ...
        @param path Chemin relatif /api/public.
        @returns JSON decode.
        """
        url = self._url(path)
        with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
            res = client.request(method, url, **kwargs)
        if res.status_code >= 400:
            raise ProspectLabError(f"{method} {path} -> {res.status_code}: {res.text[:500]}")
        if res.status_code == 204 or not res.content:
            return None
        return res.json()

    def token_info(self) -> dict:
        """GET /token/info."""
        return self._request("GET", "/token/info") or {}

    def list_groupes(self) -> List[dict]:
        """GET /groupes."""
        data = self._request("GET", "/groupes")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "groupes" in data:
            return list(data["groupes"])
        return []

    def get_groupe(self, groupe_id: int) -> dict:
        """GET /groupes/<id>."""
        data = self._request("GET", f"/groupes/{int(groupe_id)}")
        return data if isinstance(data, dict) else {}

    def list_entreprises(self, **params: Any) -> dict:
        """GET /entreprises (reponse paginee)."""
        data = self._request("GET", "/entreprises", params=params)
        return data if isinstance(data, dict) else {"items": data or []}

    def get_entreprise(self, entreprise_id: int) -> dict:
        """GET /entreprises/<id>."""
        data = self._request("GET", f"/entreprises/{int(entreprise_id)}")
        return data if isinstance(data, dict) else {}

    def list_entreprise_phones(self, entreprise_id: int, **params: Any) -> List[dict]:
        """GET /entreprises/<id>/phones."""
        data = self._request("GET", f"/entreprises/{int(entreprise_id)}/phones", params=params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return list(data.get("phones") or data.get("items") or [])
        return []

    def entreprises_by_phone(self, phone: str, **params: Any) -> dict:
        """GET /entreprises/by-phone."""
        q = {"phone": phone, **params}
        data = self._request("GET", "/entreprises/by-phone", params=q)
        return data if isinstance(data, dict) else {}

    def list_groupe_entreprises(self, groupe_id: int, **params: Any) -> dict:
        """GET /groupes/<id>/entreprises."""
        data = self._request("GET", f"/groupes/{int(groupe_id)}/entreprises", params=params)
        return data if isinstance(data, dict) else {"items": data or []}

    def iter_groupe_entreprises(
        self,
        groupe_id: int,
        *,
        limit: int = 200,
        **filters: Any,
    ) -> Iterator[dict]:
        """
        Parcourt toutes les entreprises d'un groupe (pagination).

        @param groupe_id ID ProspectLab.
        @param limit Taille page (max 1000 cote serveur).
        @param filters has_phone, statut, etc.
        @yields Dict entreprise API.
        """
        offset = 0
        page_limit = min(max(1, limit), 1000)
        while True:
            payload = self.list_groupe_entreprises(
                groupe_id,
                limit=page_limit,
                offset=offset,
                **filters,
            )
            items = payload.get("items") or payload.get("entreprises") or payload.get("data") or []
            if not isinstance(items, list):
                break
            for row in items:
                if isinstance(row, dict):
                    yield row
            total = payload.get("total")
            offset += len(items)
            if not items:
                break
            if total is not None and offset >= int(total):
                break
            if len(items) < page_limit:
                break

    def patch_entreprise_statut(
        self,
        entreprise_id: int,
        *,
        statut: str,
        note: Optional[str] = None,
    ) -> dict:
        """PATCH /entreprises/<id>/statut."""
        body: Dict[str, Any] = {"statut": statut}
        if note:
            body["note"] = note
        data = self._request("PATCH", f"/entreprises/{int(entreprise_id)}/statut", json=body)
        return data if isinstance(data, dict) else {}

    def post_entreprise_action(self, entreprise_id: int, action: str) -> dict:
        """
        POST raccourci statut (/callback, /do-not-contact, ...).

        @param action Nom sans slash.
        """
        data = self._request("POST", f"/entreprises/{int(entreprise_id)}/{action.strip('/')}")
        return data if isinstance(data, dict) else {}
