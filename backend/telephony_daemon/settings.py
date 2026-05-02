"""
Configuration du processus telephony : meme source que l'API (YAML + env).

Point d'entree explicite pour un deploiement 'service seul' sans dupliquer la logique env.
"""

from backend.core.config import Config


def load_daemon_config() -> Config:
    """Charge la configuration partagee (DATABASE_URL, TELEPHONY_*, modem, etc.)."""
    cfg = Config()
    # Ce processus EST le daemon modem : ne jamais proxifier les routes sortantes vers TELEPHONY_DAEMON_URL
    # (sinon boucle HTTP et 502 sur POST /api/v1/calls/outgoing/start si .env partage USE_TELEPHONY_DAEMON=1).
    cfg.use_telephony_daemon = False
    return cfg
