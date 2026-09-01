"""Middleware protection API interne par session UI."""

from __future__ import annotations

from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.core.config import Config
from backend.services.ui_session_service import COOKIE_NAME, derive_ui_session_secret, verify_ui_session_cookie_value


def _is_exempt_path(path: str) -> bool:
    """Indique si la route est accessible sans session UI."""
    if path in ("/health", "/docs", "/openapi.json", "/redoc"):
        return True
    if path.startswith("/api/v1/public/"):
        return True
    if path.startswith("/api/v1/auth/ui/"):
        return True
    if path.startswith("/ws/"):
        return True
    if path.startswith("/_next/"):
        return True
    if path.startswith("/api/v1/internal/"):
        return True
    if path in ("/favicon.svg", "/favicon.ico"):
        return True
    return False


class UiAuthMiddleware(BaseHTTPMiddleware):
    """Bloque /api/v1 interne si VG_UI_PASSWORD est defini et cookie absent."""

    def __init__(self, app, config: Optional[Config] = None) -> None:
        super().__init__(app)
        self._config = config or Config()

    def _session_secret(self) -> str:
        explicit = (getattr(self._config, "ui_session_secret", None) or "").strip()
        if explicit:
            return explicit
        pwd = (getattr(self._config, "ui_password", None) or "").strip()
        if pwd:
            return derive_ui_session_secret(pwd)
        return ""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        pwd = (getattr(self._config, "ui_password", None) or "").strip()
        if not pwd:
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/v1/") or _is_exempt_path(path):
            return await call_next(request)

        cookie = request.cookies.get(COOKIE_NAME)
        secret = self._session_secret()
        if verify_ui_session_cookie_value(secret, cookie):
            return await call_next(request)

        return JSONResponse(status_code=401, content={"detail": "Session UI requise."})
