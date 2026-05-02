"""Service processus dedie : modem, appels entrants/sortants, audio WebSocket."""

from backend.telephony_daemon.factory import create_telephony_app
from backend.telephony_daemon.settings import load_daemon_config

__all__ = ["create_telephony_app", "load_daemon_config"]
