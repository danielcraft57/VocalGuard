"""
Configuration du processus telephony : meme source que l'API (YAML + env).

Point d'entree explicite pour un deploiement 'service seul' sans dupliquer la logique env.
"""

from backend.core.config import Config


def load_daemon_config() -> Config:
    """Charge la configuration partagee (DATABASE_URL, TELEPHONY_*, modem, etc.)."""
    return Config()
