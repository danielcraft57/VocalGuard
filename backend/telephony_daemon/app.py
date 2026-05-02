"""Application FastAPI du daemon : fabrique dans `factory` (composition root)."""

from backend.telephony_daemon.factory import create_telephony_app

__all__ = ["create_telephony_app"]
