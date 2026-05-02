"""
Point d'entree FastAPI pour le backend VocalGuard.

Ce module expose l'application ASGI utilisee par le serveur HTTP.
Il re-utilise la configuration et la fabrique d'application existantes
dans le package `vocalguard`.
"""

from fastapi import FastAPI

from backend.api.app import create_app
from backend.api.dependencies import get_config


# Même instance que Depends(get_config) — un seul chargement .env / YAML par processus
config = get_config()

# Application FastAPI principale (utilisable par uvicorn / gunicorn)
app: FastAPI = create_app(config)

