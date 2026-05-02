"""Point d'entree ASGI pour uvicorn : `python -m uvicorn backend.telephony_daemon.main:app`."""

from backend.telephony_daemon.factory import create_telephony_app
from backend.telephony_daemon.settings import load_daemon_config

config = load_daemon_config()
app = create_telephony_app(config)
