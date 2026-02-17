"""
Couche d'acces aux donnees pour le backend VocalGuard.

Cette couche re-utilise les modeles SQLAlchemy existants definis dans
`vocalguard.database.models` tout en offrant un point d'entree clair
pour la nouvelle architecture backend.
"""

from backend.database.models import Base  # re-export pratique

