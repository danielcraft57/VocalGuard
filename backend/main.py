"""
Point d'entree FastAPI pour le backend VocalGuard.

Ce module expose l'application ASGI utilisee par le serveur HTTP.
Il re-utilise la configuration et la fabrique d'application existantes
dans le package `vocalguard`.
"""

from fastapi import FastAPI

from backend.core.config import Config
from backend.api.app import create_app


# Configuration chargee depuis le fichier YAML et les variables d'environnement
config = Config()

# Application FastAPI principale (utilisable par uvicorn / gunicorn)
app: FastAPI = create_app(config)

