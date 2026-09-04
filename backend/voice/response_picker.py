"""
Choix de reponse d'intent sans se repeter (variantes + historique).
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Sequence, Tuple


# Relances courtes si on retombe sur le meme intent sans variante libre.
_STREAK_BRIDGES = (
    "D'accord, je note. Vous voulez preciser autre chose ?",
    "C'est note. Je peux aussi vous orienter vers un rendez-vous, un devis ou un message.",
    "Oui, on reste sur ce sujet. Dites-moi ce qu'il manque.",
    "Je vous ai deja indique ca. Autre besoin ?",
)


def normalize_reply_key(text: str) -> str:
    """
    Cle de comparaison pour l'historique des reponses.

    @param text Phrase.
    @returns Texte normalise.
    """
    return " ".join((text or "").strip().lower().split())


def select_response(
    responses: Sequence[str],
    *,
    recent_replies: Sequence[str] = (),
    same_tag_streak: int = 0,
) -> Tuple[str, int]:
    """
    Choisit une reponse en evitant celles deja dites recemment.

    Ordre :
    1. Variantes jamais dites dans ``recent_replies`` (ordre catalogue).
    2. Variante la moins recente dans l'historique.
    3. Si meme tag d'affilee et aucune variante neuve → pont de relance.

    @param responses Textes candidats (ordre position).
    @param recent_replies Reponses deja envoyees (plus recent en fin).
    @param same_tag_streak Nb de fois consecutives ou ce tag a gagne.
    @returns (texte, index dans responses) ; index -1 si pont.
    """
    cleaned: List[Tuple[int, str]] = []
    for idx, raw in enumerate(responses):
        t = str(raw or "").strip()
        if t:
            cleaned.append((idx, t))
    if not cleaned:
        return ("D'accord.", -1)

    recent_keys = [normalize_reply_key(r) for r in recent_replies if r]
    recent_set = set(recent_keys)

    fresh = [(i, t) for i, t in cleaned if normalize_reply_key(t) not in recent_set]
    if fresh:
        return (fresh[0][1], fresh[0][0])

    if same_tag_streak >= 1:
        bridge = _STREAK_BRIDGES[same_tag_streak % len(_STREAK_BRIDGES)]
        if normalize_reply_key(bridge) not in recent_set:
            return (bridge, -1)

    # Toutes deja dites : celle dite le plus longtemps.
    best_i, best_t = cleaned[0]
    best_age = -1
    for i, t in cleaned:
        key = normalize_reply_key(t)
        try:
            age = len(recent_keys) - 1 - recent_keys[::-1].index(key)
        except ValueError:
            age = len(recent_keys)
        if age > best_age:
            best_age = age
            best_i, best_t = i, t
    return (best_t, best_i)


def same_tag_streak(tag: str, recent_tags: Sequence[str]) -> int:
    """
    Compte les victoires consecutives du tag en fin d'historique.

    @param tag Tag courant.
    @param recent_tags Historique (plus recent en fin).
    @returns Streak (>= 0).
    """
    if not tag:
        return 0
    n = 0
    for t in reversed(recent_tags):
        if str(t or "") == tag:
            n += 1
        else:
            break
    return n


def apply_recent_tag_penalty(
    predictions: Sequence[Dict[str, Any]],
    recent_tags: Sequence[str],
    *,
    base_penalty: float = 0.10,
    streak_extra: float = 0.08,
) -> List[Dict[str, Any]]:
    """
    Adoucit le score des tags recemment choisis pour diversifier.

    Renormalise ensuite. Utile si deux intents sont proches.

    @param predictions Liste {tag, score}.
    @param recent_tags Historique tags (fin = plus recent).
    @param base_penalty Malus si tag vu recemment.
    @param streak_extra Malus par repetition consecutive.
    @returns Nouvelle liste triee.
    """
    if not predictions:
        return []
    streak = same_tag_streak(str(recent_tags[-1]) if recent_tags else "", recent_tags)
    recent_set = {str(t) for t in recent_tags[-4:] if t}
    last = str(recent_tags[-1]) if recent_tags else ""

    adjusted: List[Dict[str, Any]] = []
    for row in predictions:
        tag = str(row.get("tag") or "")
        score = float(row.get("score") or 0.0)
        malus = 0.0
        if tag and tag in recent_set:
            malus += base_penalty
        if tag and tag == last:
            malus += streak_extra * max(1, streak)
        adjusted.append({"tag": tag, "score": max(0.0, score - malus)})

    total = sum(r["score"] for r in adjusted) or 1.0
    for r in adjusted:
        r["score"] = float(r["score"] / total)
    adjusted.sort(key=lambda r: r["score"], reverse=True)
    return adjusted


def variant_wav_basename(tag: str, response_index: int) -> str:
    """
    Basename WAV pour une variante de reponse.

    @param tag Tag intent.
    @param response_index Index (0 = principal kb_tag).
    @returns Nom sans extension.
    """
    clean = (tag or "").strip() or "intent"
    if response_index <= 0:
        return f"kb_{clean}"
    return f"kb_{clean}_r{int(response_index)}"


def reply_content_token(text: str) -> str:
    """
    Court hash stable d'un texte (debug / cache).

    @param text Phrase.
    @returns 8 hex.
    """
    return hashlib.sha1(normalize_reply_key(text).encode("utf-8")).hexdigest()[:8]
