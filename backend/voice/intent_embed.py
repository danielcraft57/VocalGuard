"""
Embeddings locaux deterministes pour intents (hashing n-grams).

Pas de modele externe : stable en CI et sur le LAN. Dimension fixe pour pgvector.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable, List, Sequence

# Dimension alignee avec la colonne Vector / migration pgvector.
EMBED_DIM = 384

_TOKEN_RE = re.compile(r"[a-z0-9àâäéèêëïîôùûüç]+", re.IGNORECASE)


def normalize_intent_text(text: str) -> str:
    """
    Normalise un texte FR pour matching / embedding.

    @param text Phrase brute.
    @returns Texte minuscule, espaces reduits.
    """
    raw = (text or "").strip().lower()
    raw = raw.replace("'", "'").replace("'", "'")
    return re.sub(r"\s+", " ", raw)


def _tokens(text: str) -> List[str]:
    """Decoupe en tokens alphanumeriques."""
    return _TOKEN_RE.findall(normalize_intent_text(text))


def _ngrams(tokens: Sequence[str], n: int) -> Iterable[str]:
    """Genere des n-grams de tokens."""
    if n <= 1:
        for t in tokens:
            yield t
        return
    for i in range(0, max(0, len(tokens) - n + 1)):
        yield " ".join(tokens[i : i + n])


def _bucket(feature: str, dim: int) -> int:
    """
    Hash d'une feature vers un index de vecteur.

    @param feature Chaine a hasher.
    @param dim Dimension cible.
    @returns Index 0..dim-1.
    """
    digest = hashlib.sha256(feature.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little") % dim


def embed_text(text: str, *, dim: int = EMBED_DIM) -> List[float]:
    """
    Produit un embedding L2-normalise via hashing trick (unigrammes + bigrammes).

    @param text Phrase a encoder.
    @param dim Dimension du vecteur.
    @returns Liste de floats de longueur ``dim``.
    """
    vec = [0.0] * dim
    tokens = _tokens(text)
    if not tokens:
        return vec
    features: List[str] = []
    features.extend(_ngrams(tokens, 1))
    features.extend(_ngrams(tokens, 2))
    # Caracteres 3-grams pour robustesse orthographe orale.
    compact = "".join(tokens)
    for i in range(0, max(0, len(compact) - 2)):
        features.append(f"c:{compact[i : i + 3]}")
    for feat in features:
        idx = _bucket(feat, dim)
        sign = 1.0 if (hashlib.md5(feat.encode("utf-8")).digest()[0] & 1) == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 1e-12:
        return vec
    return [v / norm for v in vec]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """
    Similarite cosinus entre deux vecteurs.

    @param a Premier vecteur.
    @param b Second vecteur.
    @returns Score dans [-1, 1].
    """
    n = min(len(a), len(b))
    if n <= 0:
        return 0.0
    return float(sum(float(a[i]) * float(b[i]) for i in range(n)))
