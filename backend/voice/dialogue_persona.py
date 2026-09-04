"""
Persona de dialogue : contexte, patience, defauts humains (agacement, ironie).

Sans LLM : regles + banques de phrases pour faire avancer la conversation
quand le predict d'intent tourne en boucle (ex. bonjour x N).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.voice.response_picker import normalize_reply_key, same_tag_streak

# Intents "one-shot" : une fois traites, on ne les rejoue pas tels quels.
ONESHOT_TAGS = frozenset(
    {
        "salutation",
        "remerciements",
        "silence_attente",
        "hors_sujet",
    }
)

# Apres ces tags, on privilegie une suite utile.
FOLLOW_UP_BOOST: Dict[str, Tuple[str, ...]] = {
    "salutation": ("aide_menu", "services_info", "prise_rdv", "tarifs_devis", "absent_laisser_message"),
    "aide_menu": ("prise_rdv", "tarifs_devis", "absent_laisser_message", "prendre_coordonnees"),
    "remerciements": ("fin", "aide_menu"),
    "incompris": ("aide_menu", "prise_rdv", "absent_laisser_message"),
}

# Salutations / fillers detectes cote utilisateur.
_GREETING_RE = re.compile(
    r"\b(bonjour|bonsoir|salut|hello|all[oô]|hey|coucou)\b",
    re.IGNORECASE,
)
_THANKS_RE = re.compile(r"\b(merci|thanks)\b", re.IGNORECASE)
_FILLER_RE = re.compile(
    r"^\s*(euh+|hum+|all[oô]\s*all[oô]|y\s*a\s*quelqu.?un|vous\s*[eê]tes\s*l[aà])\s*[.?!]*\s*$",
    re.IGNORECASE,
)

# Insultes FR courantes (detection lexicale, pas de reponse toxique en retour).
_INSULT_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:connard|connasse|abruti|imb[eé]cile|idiot|d[eé]bile|cr[eé]tin|boloss)\b|"
    r"\b(?:salope|pute|encul[eé]|nique(?:r|)\b|ntm|fdp|tg)\b|"
    r"\b(?:ta\s+gueule|ferme[- ]?la|casse[- ]toi|va\s+te\s+faire)\b|"
    r"\b(?:merde|putain|bordel)\b|"
    r"\bcon(?:ne)?\b"
    r")"
)


@dataclass
class DialogueMood:
    """
    Etat emotionnel simple du repondeur.

    @param patience 1.0 = zen, 0.0 = a bout.
    @param tone calm | firm | annoyed | ironic.
    @param user_repeat Combien de fois le user repete quasiment la meme chose.
    @param tag_streak Streak du tag predit.
    """

    patience: float
    tone: str
    user_repeat: int
    tag_streak: int


# Banques persona : index = intensite (0..)
_PERSONA: Dict[str, Tuple[str, ...]] = {
    "repeat_hello": (
        "Oui, bonjour... et ensuite ?",
        "On s'est deja salues. Que puis-je faire pour vous ?",
        "Toujours bonjour ? Dites-moi plutot le motif : rendez-vous, devis, message...",
        "Je suis une messagerie, pas un perroquet. Un besoin concret, peut-etre ?",
        "Bon. Si c'est juste pour s'entrainer a dire bonjour, on a fini. Sinon, je vous ecoute.",
    ),
    "repeat_thanks": (
        "Avec plaisir. Autre chose ?",
        "De rien. On avance ?",
        "Oui, merci a vous aussi. Un rendez-vous, un message ?",
        "On a compris le merci. Besoin d'autre chose, ou on raccroche ?",
    ),
    "repeat_same": (
        "Vous venez de le dire. Je peux vous aider autrement ?",
        "Je note... mais c'est la meme demande. Precisez un detail ?",
        "On tourne en rond. Essayez : devis, rendez-vous, ou laisser un message.",
        "Ok, j'ai bien entendu. Une seule fois suffit. Que fait-on maintenant ?",
    ),
    "filler": (
        "Oui, je suis la. En quelques mots ?",
        "Toujours la. Rendez-vous, devis, message ?",
        "Je vous entends. Evitez le silence, dites le motif.",
    ),
    "nudge_after_hello": (
        "Dites-moi en une phrase ce dont vous avez besoin.",
        "Je peux prendre un rendez-vous, un devis, ou un message. Qu'est-ce que ce sera ?",
        "Allez-y : motif de l'appel ?",
    ),
    "loop_generic": (
        "On revient au meme point. Changeons d'angle ?",
        "Hmm. Autre piste : horaires, coordonnees, ou un rappel ?",
        "Je commence a tourner en boucle moi aussi. Une option claire, s'il vous plait.",
    ),
    "insult": (
        "Je reste courtois. Reformulez sans injure, je pourrai vous aider.",
        "Les insultes, ca n'avance pas. Motif de l'appel, s'il vous plait.",
        "Ok, on a compris le ton. Ici c'est une messagerie pro. Rendez-vous, devis, message ?",
        "Charmant. Quand vous aurez fini le spectacle, je suis toujours la pour un vrai besoin.",
        "Bon, on s'arrete la. Rappelez quand vous serez pret a parler correctement. Au revoir.",
    ),
}


def contains_insult(text: str) -> bool:
    """
    Detecte une injure / propos agressif dans le texte user.

    @param text Message.
    @returns True si hit lexical.
    """
    return bool(_INSULT_RE.search(text or ""))


def count_insult_turns(recent_user_texts: Sequence[str], current: str) -> int:
    """
    Nombre de tours insultants recents (y compris le courant).

    @param recent_user_texts Historique.
    @param current Texte actuel.
    @returns Compteur (>= 1 si current insultant).
    """
    n = 1 if contains_insult(current) else 0
    for prev in recent_user_texts[-6:]:
        if contains_insult(prev):
            n += 1
    return n


def normalize_utterance(text: str) -> str:
    """
    Normalise une phrase utilisateur pour comparer les repetitions.

    @param text Brut.
    @returns Cle.
    """
    t = normalize_reply_key(text)
    t = re.sub(r"[!?.…]+$", "", t).strip()
    return t


def count_user_repeats(text: str, recent_user_texts: Sequence[str]) -> int:
    """
    Compte les enonces user consecutifs (fin) proches du texte courant.

    @param text Nouveau message.
    @param recent_user_texts Historique user (fin = recent).
    @returns Nombre de repetitions consecutives deja presentes (0 si nouveau).
    """
    key = normalize_utterance(text)
    if not key:
        return 0
    n = 0
    for prev in reversed(recent_user_texts):
        pk = normalize_utterance(prev)
        if not pk:
            continue
        if pk == key or (len(key) >= 4 and (key in pk or pk in key)):
            n += 1
        else:
            break
    return n


def compute_mood(
    *,
    recent_tags: Sequence[str],
    recent_user_texts: Sequence[str],
    user_text: str,
    predicted_tag: str = "",
) -> DialogueMood:
    """
    Estime patience / ton a partir du contexte.

    @returns DialogueMood.
    """
    user_repeat = count_user_repeats(user_text, recent_user_texts)
    past_streak = same_tag_streak(predicted_tag, recent_tags) if predicted_tag else 0
    # Si on recommit le meme tag, le streak effectif apres ce tour
    effective_streak = past_streak + (1 if predicted_tag else 0)

    hit = 0.0
    hit += 0.22 * user_repeat
    hit += 0.18 * max(0, effective_streak - 1)
    oneshot_hits = sum(1 for t in recent_tags[-6:] if t in ONESHOT_TAGS)
    hit += 0.08 * oneshot_hits
    if _GREETING_RE.search(user_text or "") and "salutation" in recent_tags:
        hit += 0.25 + 0.15 * user_repeat
    if contains_insult(user_text or ""):
        hit += 0.35 + 0.12 * max(0, count_insult_turns(recent_user_texts, user_text) - 1)
    patience = max(0.0, min(1.0, 1.0 - hit))

    if patience >= 0.75:
        tone = "calm"
    elif patience >= 0.5:
        tone = "firm"
    elif patience >= 0.28:
        tone = "annoyed"
    else:
        tone = "ironic"

    return DialogueMood(
        patience=patience,
        tone=tone,
        user_repeat=user_repeat,
        tag_streak=max(0, effective_streak - 1),
    )


def _pick_persona(bucket: str, intensity: int, recent_replies: Sequence[str]) -> str:
    """Choisit une phrase persona en evitant l'historique recent."""
    lines = _PERSONA.get(bucket) or _PERSONA["loop_generic"]
    intensity = max(0, min(intensity, len(lines) - 1))
    # Essaie intensite puis voisines
    order = list(range(intensity, len(lines))) + list(range(intensity - 1, -1, -1))
    recent = {normalize_reply_key(r) for r in recent_replies if r}
    for i in order:
        cand = lines[i]
        if normalize_reply_key(cand) not in recent:
            return cand
    return lines[intensity]


def reshape_predictions(
    predictions: Sequence[Dict[str, Any]],
    *,
    recent_tags: Sequence[str],
    user_text: str,
) -> List[Dict[str, Any]]:
    """
    Repondre le ranking : malus oneshot, boost de suite logique.

    @param predictions Scores bruts.
    @param recent_tags Tags deja commits.
    @param user_text Texte user.
    @returns Liste renormalisee.
    """
    if not predictions:
        return []

    seen = {str(t) for t in recent_tags if t}
    last = str(recent_tags[-1]) if recent_tags else ""
    greeting_again = bool(_GREETING_RE.search(user_text or "")) and "salutation" in seen
    only_greeting = bool(_GREETING_RE.fullmatch(normalize_utterance(user_text) or "x") or (
        _GREETING_RE.search(user_text or "") and len(normalize_utterance(user_text).split()) <= 3
    ))

    adjusted: List[Dict[str, Any]] = []
    for row in predictions:
        tag = str(row.get("tag") or "")
        score = float(row.get("score") or 0.0)
        malus = 0.0
        bonus = 0.0

        if tag in seen and tag in ONESHOT_TAGS:
            malus += 0.45
        if greeting_again and tag == "salutation":
            malus += 0.55
        if tag and recent_tags and tag == last:
            malus += 0.20

        # Suite naturelle apres salutation
        if last in FOLLOW_UP_BOOST and tag in FOLLOW_UP_BOOST[last]:
            bonus += 0.18
        if greeting_again and tag in ("aide_menu", "services_info", "prise_rdv"):
            bonus += 0.25
        if only_greeting and "salutation" in seen and tag == "aide_menu":
            bonus += 0.2

        adjusted.append({"tag": tag, "score": max(0.0, score - malus + bonus)})

    total = sum(r["score"] for r in adjusted) or 1.0
    for r in adjusted:
        r["score"] = float(r["score"] / total)
    adjusted.sort(key=lambda r: r["score"], reverse=True)
    return adjusted


def persona_override(
    *,
    user_text: str,
    predicted_tag: str,
    mood: DialogueMood,
    recent_tags: Sequence[str],
    recent_replies: Sequence[str],
    recent_user_texts: Sequence[str] = (),
) -> Optional[Tuple[str, str, Optional[str]]]:
    """
    Remplace parfois la reponse catalogue par une replique plus humaine.

    @returns (reply, reason, action_override) ou None.
    """
    text = user_text or ""
    seen = {str(t) for t in recent_tags if t}
    intensity = max(mood.user_repeat, mood.tag_streak, int(round((1.0 - mood.patience) * 4)))

    if contains_insult(text):
        insult_n = count_insult_turns(recent_user_texts, text)
        intensity = max(intensity, insult_n - 1, int(round((1.0 - mood.patience) * 4)))
        action = "hangup_soft" if insult_n >= 3 or intensity >= 4 else None
        return (
            _pick_persona("insult", intensity, recent_replies),
            "insult",
            action,
        )

    if _FILLER_RE.match(text.strip()):
        return _pick_persona("filler", intensity, recent_replies), "filler", None

    if _GREETING_RE.search(text) and "salutation" in seen:
        return _pick_persona("repeat_hello", intensity, recent_replies), "repeat_hello", None

    if _THANKS_RE.search(text) and "remerciements" in seen:
        return _pick_persona("repeat_thanks", intensity, recent_replies), "repeat_thanks", None

    if mood.user_repeat >= 1:
        return _pick_persona("repeat_same", intensity, recent_replies), "repeat_same", None

    # Apres un vrai bonjour, si on retombe encore sur salutation malgre reshape
    if predicted_tag == "salutation" and "salutation" in seen:
        return _pick_persona("nudge_after_hello", intensity, recent_replies), "nudge_after_hello", None

    if predicted_tag in ONESHOT_TAGS and predicted_tag in seen and mood.tag_streak >= 1:
        return _pick_persona("loop_generic", intensity, recent_replies), "loop_generic", None

    return None


def flavor_catalog_reply(reply: str, mood: DialogueMood) -> str:
    """
    Leger assaisonnement humain sur une reponse catalogue (sans tout casser).

    @param reply Texte intent.
    @param mood Humeur.
    @returns Texte eventuellement nuance.
    """
    text = (reply or "").strip()
    if not text:
        return text
    if mood.tone == "calm":
        return text
    if mood.tone == "firm" and not text.endswith("?"):
        return text.rstrip(".") + ". On avance ?"
    if mood.tone == "annoyed":
        prefix = ("Bon... ", "D'accord, alors. ", "Ok. ")[int(mood.patience * 10) % 3]
        if text.lower().startswith(prefix.lower().strip()):
            return text
        return prefix + text[0].lower() + text[1:] if len(text) > 1 else prefix + text
    if mood.tone == "ironic":
        tails = (
            " ...si on veut bien avancer.",
            " — frein a main serre, hein.",
            " (je me repete, je sais.)",
        )
        tail = tails[int((1 - mood.patience) * 10) % 3]
        if any(t.strip() in text for t in tails):
            return text
        return text.rstrip(".") + tail
    return text


def resolve_dialogue_reply(
    *,
    user_text: str,
    predictions: Sequence[Dict[str, Any]],
    recent_tags: Sequence[str],
    recent_replies: Sequence[str],
    recent_user_texts: Sequence[str],
    catalog_responses: Sequence[str],
) -> Dict[str, Any]:
    """
    Pipeline complet : reshape → mood → persona ou catalogue flavore.

    @param catalog_responses Reponses de l'intent gagnant (peut etre vide).
    @returns Dict pour l'API chat / call_manager.
    """
    from backend.voice.response_picker import select_response

    reshaped = reshape_predictions(
        predictions, recent_tags=recent_tags, user_text=user_text
    )
    tag = str(reshaped[0]["tag"]) if reshaped else ""
    score = float(reshaped[0]["score"]) if reshaped else 0.0
    mood = compute_mood(
        recent_tags=recent_tags,
        recent_user_texts=recent_user_texts,
        user_text=user_text,
        predicted_tag=tag,
    )

    override = persona_override(
        user_text=user_text,
        predicted_tag=tag,
        mood=mood,
        recent_tags=recent_tags,
        recent_replies=recent_replies,
        recent_user_texts=recent_user_texts,
    )

    if override is not None:
        reply, reason, action_override = override
        display_tag = "insulte" if reason == "insult" else (tag or None)
        return {
            "reply": reply,
            "tag": display_tag,
            "score": score if reason != "insult" else max(score, 0.99),
            "response_index": -1,
            "persona_reason": reason,
            "action": action_override,
            "mood": {
                "patience": round(mood.patience, 3),
                "tone": mood.tone,
                "user_repeat": mood.user_repeat,
                "tag_streak": mood.tag_streak,
            },
            "top_predictions": reshaped,
        }

    streak = same_tag_streak(tag, recent_tags)
    reply, response_index = select_response(
        catalog_responses,
        recent_replies=recent_replies,
        same_tag_streak=streak,
    )
    reply = flavor_catalog_reply(reply, mood)
    return {
        "reply": reply,
        "tag": tag or None,
        "score": score,
        "response_index": response_index,
        "persona_reason": None,
        "action": None,
        "mood": {
            "patience": round(mood.patience, 3),
            "tone": mood.tone,
            "user_repeat": mood.user_repeat,
            "tag_streak": mood.tag_streak,
        },
        "top_predictions": reshaped,
    }
