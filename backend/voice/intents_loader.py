"""
Chargeur d'intents IVR depuis un fichier YAML.

Utilise par le script test_patterns_voice pour associer des strategies
question-reponse a des fichiers WAV telephoniques (8 kHz).
"""

import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional

from loguru import logger


def _default_intent() -> Dict[str, Any]:
    """Intent par defaut si aucun pattern ne matche."""
    return {
        "name": "incompris",
        "keywords": [],
        "response": "Je n ai pas bien compris. Pouvez-vous reformuler votre question simplement ?",
        "filename": "ivr_incompris.wav",
    }


def _default_exit_intent() -> Dict[str, Any]:
    """Intent de sortie (au revoir)."""
    return {
        "name": "fin",
        "keywords": ["au revoir", "bye", "a bientot", "quitter", "terminer"],
        "response": "Au revoir. Merci pour votre appel.",
        "filename": "ivr_fin.wav",
    }


def load_intents_ivr(config_path: Optional[Path] = None, base_path: Optional[Path] = None) -> tuple:
    """
    Charge les intents IVR depuis un fichier YAML.

    Args:
        config_path: Chemin direct vers le fichier intents (ex: config/intents_ivr.yaml).
        base_path: Racine du projet pour chercher config/intents_ivr.yaml si config_path est None.

    Returns:
        Tuple (intents, default_intent, exit_intent):
        - intents: liste de dicts tries par priority (desc), chaque dict a name, keywords, response, filename, priority, exact_match
        - default_intent: dict pour "incompris"
        - exit_intent: dict pour "au revoir"
    """
    if config_path is None and base_path is not None:
        config_path = base_path / "config" / "intents_ivr.yaml"
    if config_path is None:
        # Fallback: chemin relatif au package backend/voice
        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "intents_ivr.yaml"

    if not config_path.exists():
        # Secours: fichier d'exemple (template versionne, intents_ivr.yaml ignore par git)
        example_path = config_path.parent / "intents_ivr.example.yaml"
        if example_path.exists():
            config_path = example_path
            logger.debug(f"Utilisation du fichier exemple: {config_path}")
        else:
            logger.warning(f"Fichier intents IVR non trouve: {config_path}. Utilisation des intents par defaut.")
            return _default_intents_in_memory(), _default_intent(), _default_exit_intent()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.exception(f"Erreur lecture intents_ivr.yaml: {e}")
        return _default_intents_in_memory(), _default_intent(), _default_exit_intent()

    if not data:
        return _default_intents_in_memory(), _default_intent(), _default_exit_intent()

    raw_intents = data.get("intents") or []
    intents: List[Dict[str, Any]] = []
    for item in raw_intents:
        intents.append({
            "name": item.get("name", "unknown"),
            "keywords": [str(k).lower() for k in item.get("keywords") or []],
            "response": item.get("response", ""),
            "filename": item.get("filename", "ivr_unknown.wav"),
            "priority": int(item.get("priority", 0)),
            "exact_match": bool(item.get("exact_match", False)),
        })

    intents.sort(key=lambda x: x["priority"], reverse=True)

    default = data.get("default_intent") or {}
    default_intent = {
        "name": default.get("name", "incompris"),
        "keywords": [],
        "response": default.get("response", _default_intent()["response"]),
        "filename": default.get("filename", "ivr_incompris.wav"),
    }

    exit_cfg = data.get("exit_intent") or {}
    exit_intent = {
        "name": exit_cfg.get("name", "fin"),
        "keywords": [str(k).lower() for k in exit_cfg.get("keywords", _default_exit_intent()["keywords"])],
        "response": exit_cfg.get("response", _default_exit_intent()["response"]),
        "filename": exit_cfg.get("filename", "ivr_fin.wav"),
    }

    logger.debug(f"Intents IVR charges: {len(intents)} intents depuis {config_path}")
    return intents, default_intent, exit_intent


def _default_intents_in_memory() -> List[Dict[str, Any]]:
    """Liste d'intents par defaut si le YAML est absent."""
    return [
        {"name": "salutation", "keywords": ["bonjour"], "response": "Bonjour, vous etes bien sur la ligne de demonstration de VocalGuard.", "filename": "ivr_bonjour.wav", "priority": 10, "exact_match": False},
        {"name": "horaires", "keywords": ["horaire"], "response": "Nos horaires d ouverture sont du lundi au vendredi, de neuf heures a dix-huit heures.", "filename": "ivr_horaires.wav", "priority": 8, "exact_match": False},
        {"name": "aide", "keywords": ["aide", "besoin"], "response": "Vous pouvez poser une question simple, par exemple pour les horaires ou pour laisser un message.", "filename": "ivr_aide.wav", "priority": 7, "exact_match": False},
    ]


def find_intent(
    user_text: str,
    intents: List[Dict[str, Any]],
    default_intent: Dict[str, Any],
    exit_intent: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Retourne l'intent qui correspond au texte utilisateur.

    On teste d'abord si le texte correspond a l'intent de sortie (exit_intent),
    puis les intents dans l'ordre de priorite. Si aucun ne matche, on retourne default_intent.

    Args:
        user_text: Phrase reconnue (STT).
        intents: Liste d'intents charges (deja triee par priority).
        default_intent: Intent "incompris".
        exit_intent: Intent "au revoir".

    Returns:
        Un dict avec au moins name, response, filename (et eventuellement keywords).
    """
    text = (user_text or "").lower().strip()
    if not text:
        return default_intent

    # Test sortie en premier
    exit_kw = exit_intent.get("keywords") or []
    if any(kw in text for kw in exit_kw):
        return exit_intent

    for intent in intents:
        keywords = intent.get("keywords") or []
        if not keywords:
            continue
        exact = intent.get("exact_match", False)
        if exact:
            if all(kw in text for kw in keywords):
                return intent
        else:
            if any(kw in text for kw in keywords):
                return intent

    return default_intent
