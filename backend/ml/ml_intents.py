"""
Classification d intents a partir des fichiers intents JSON DanielCraft (`data/`).

Architecture simple:
  - vecteur TF-IDF caracteres (`character n-grams`), robustes au bruit STT court
  - regression logistique multi-classes avec probabilites calibrees

Artifacts attendus dans `models/` :
  - `intent_classifier.pkl` (Pipeline sklearn avec vectorizer et classifier calibres)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

import joblib
from loguru import logger


DEFAULT_MODEL_PATH_REL = Path("models") / "intent_classifier.pkl"


@dataclass
class PredictedIntent:
    """Prediction ML (tag + probabilite associe)."""

    tag: str
    score: float  # probabilite calibree


class JsonMarketingIntentStore:
    """
    Charge des intents JSON sous forme { "intents": [ {tag, patterns, responses}, ... ] }.

    Responsable aussi de fournir un mapping tag -> liste de reponses utilisables hors ligne.
    """

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        self.glob_pattern = os.environ.get(
            "INTENTS_JSON_GLOB",
            str(Path("data") / "intents_danielcraft_*.json"),
        )

        self._responses_by_tag: Dict[str, List[str]] = {}
        self._pattern_texts_for_tag: Dict[str, List[str]] = {}

    def reload(self) -> None:
        self._responses_by_tag = {}
        self._pattern_texts_for_tag = {}
        globs_to_scan = [self.glob_pattern.strip()]
        scanned_files: List[Path] = []
        project_root = self.base_path
        # Supporte soit un motif simple, soit plusieurs motifs separes par ;
        globs_flat: List[str] = []
        for piece in ";".join(globs_to_scan).split(";"):
            piece = piece.strip()
            if piece:
                globs_flat.append(piece)

        for pattern in globs_flat:
            for path in sorted(project_root.glob(pattern)):
                if path.is_file() and path.suffix.lower() == ".json":
                    scanned_files.append(path)

        if not scanned_files:
            logger.warning(
                "Aucun fichier intents DanielCraft trouve pour le ML (patterns vides)."
            )

        duplicate_tags: MutableMapping[str, int] = {}
        loaded_intents_total = 0

        for file_path in scanned_files:
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Erreur lecture intents JSON '{}': {}", file_path, exc)
                continue

            intents = payload.get("intents") or []
            loaded_intents_total += len(intents)

            for intent in intents:
                tag_raw = intent.get("tag")
                if not tag_raw:
                    continue
                tag = str(tag_raw)
                duplicate_tags[tag] = duplicate_tags.get(tag, 0) + 1

                responses = intent.get("responses") or []
                patterns = intent.get("patterns") or []

                if responses:
                    # On conserve la derniere liste rencontrée si plusieurs fichiers repetent exactement ce tag,
                    # mais si un tag existe deja avec des valeurs différentes, on fusionne avec prudence.
                    existing_resp = self._responses_by_tag.get(tag)
                    clean_responses = [str(r).strip() for r in responses if str(r).strip()]
                    if existing_resp is None:
                        self._responses_by_tag[tag] = clean_responses
                    elif clean_responses and clean_responses != existing_resp:
                        merged = []
                        merged.extend(existing_resp)
                        for sentence in clean_responses:
                            if sentence not in merged:
                                merged.append(sentence)
                        self._responses_by_tag[tag] = merged

                clean_patterns = [str(p).strip().lower() for p in patterns if str(p).strip()]
                if clean_patterns:
                    bucket = self._pattern_texts_for_tag.setdefault(tag, [])
                    for pattern in clean_patterns:
                        if pattern not in bucket:
                            bucket.append(pattern)

        logger.info(
            "Intents ML JSON charges: fichiers={}, intents declarés={}, tags uniques={}",
            len(scanned_files),
            loaded_intents_total,
            len(self._responses_by_tag),
        )

        if duplicate_tags:
            collisions = sorted([t for t, c in duplicate_tags.items() if c > 1])
            if collisions:
                logger.warning(
                    "Tags en double declares dans plusieurs entrées JSON pour le meme tag: exemples {}",
                    collisions[:15],
                )

    def get_responses_for_tag(self, tag: str) -> List[str]:
        return list(self._responses_by_tag.get(tag) or [])

    def augment_training_examples(self, tag: str) -> List[str]:
        """
        Génére des phrases d entraînement supplémentaires légères à partir des motifs existants.

        Attention: on reste léger pour eviter explosions de combinatoire.
        """
        patterns = list(self._pattern_texts_for_tag.get(tag) or [])
        extras: List[str] = []

        fillers = ["", "oui ", "hum ", "euh ", "pour info ", ""]
        suffixes = [
            "",
            " alors",
            " s il vous plait",
            " rapidement",
        ]

        original = patterns[:]

        # Variantes simples (prefix/fillers)
        for p in original:
            p_low = p.lower().strip()
            if not p_low:
                continue
            if not p_low.endswith("."):
                p_sentence = p_low + "."
                if p_sentence not in patterns:
                    patterns.append(p_sentence)
            else:
                p_trim = p_low.rstrip(".")
                if p_trim and p_trim not in patterns:
                    patterns.append(p_trim)

            for filler in fillers:
                if not filler:
                    continue
                variant = (filler + p_low).strip()
                if variant not in patterns:
                    patterns.append(variant)
            for suffix in suffixes:
                if suffix:
                    variant = (p_low + suffix).strip()
                    if variant not in patterns:
                        patterns.append(variant)

        extras.extend(patterns)

        # Petits templates marketing simples contextualisés
        if tag.startswith(("n4_", "offer_", "pricing")):
            for base in original[: min(15, len(original))]:
                for template in ("je vous appelle au sujet de {s}", "{s}", "question simple: {s}"):
                    text = template.format(s=base)
                    extras.append(text)

        cleaned: List[str] = []
        seen: MutableMapping[str, int] = {}
        for phrase in extras:
            key = phrase.strip().lower()
            if len(key) < 2:
                continue
            if key not in seen:
                seen[key] = 1
                cleaned.append(key)

        return cleaned


class MlMarketingIntentPredictor:
    """
    Wrapper autour du joblib sklearn.
    """

    def __init__(self, base_path: Path, model_rel_path: Path = DEFAULT_MODEL_PATH_REL) -> None:
        self.base_path = base_path
        self.model_rel_path = Path(model_rel_path)
        explicit = os.environ.get("INTENT_ML_MODEL_PATH", "").strip()
        if explicit:
            self.model_path = Path(explicit)
        else:
            self.model_path = self.base_path / self.model_rel_path
        self._pipeline: Optional[Any] = None

    def reload(self) -> None:
        if not self.model_path.exists():
            self._pipeline = None
            logger.warning(
                "Modele intents ML absent: {} -- entrainez via scripts/train_intent_classifier.py",
                self.model_path,
            )
            return
        try:
            self._pipeline = joblib.load(self.model_path)
            logger.info("Modele intents ML charge: {}", self.model_path)
        except Exception as exc:
            logger.exception("Impossible de charger le modele ML intents depuis {}: {}", self.model_path, exc)
            self._pipeline = None

    def predict(self, text: str, top_k: int = 1) -> List[PredictedIntent]:
        if self._pipeline is None or not text:
            return []
        trimmed = text.strip().lower()
        if not trimmed:
            return []
        predict_fn = getattr(self._pipeline, "predict_proba", None)
        if predict_fn is None:
            return []

        scores = predict_fn([trimmed])[0]
        labels = getattr(self._pipeline.named_steps["clf"], "classes_", None)
        if labels is None:
            return []

        scored_pairs: List[Tuple[float, Any]] = []
        for label, score in zip(labels, scores):
            scored_pairs.append((float(score), label))

        scored_pairs.sort(key=lambda pair: pair[0], reverse=True)
        intents: List[PredictedIntent] = []
        for score, raw_label in scored_pairs[:top_k]:
            intents.append(PredictedIntent(tag=str(raw_label), score=score))

        return intents


class CommercialMlConversationBrain:
    """
    Orchestrateur: JSON intents + predicteur sklearn + seuil configurable.
    """

    def __init__(self, base_path: Optional[Path] = None) -> None:
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self.store = JsonMarketingIntentStore(self.base_path)
        self.predictor = MlMarketingIntentPredictor(self.base_path)

        self.enabled = os.environ.get("COMMERCIAL_ML_INTENTS_ENABLED", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        self.threshold = float(os.environ.get("COMMERCIAL_ML_CONF_THRESHOLD", "0.45"))

        self.reload()

    def reload(self) -> None:
        self.store.reload()
        self.predictor.reload()

    def generate_reply_if_confident(self, text: str) -> Optional[str]:
        if not self.enabled:
            return None

        preds = self.predictor.predict(text, top_k=1)
        if not preds:
            return None

        best = preds[0]
        if best.score < self.threshold:
            logger.debug(
                "Intent ML '{}' score trop bas ({:.3f}) < seuil {:.3f}",
                best.tag,
                best.score,
                self.threshold,
            )
            return None

        replies = self.store.get_responses_for_tag(best.tag)
        if not replies:
            logger.warning("Intent ML detecte '{}' mais aucune reponse JSON associee", best.tag)
            return None

        import random

        chosen = random.choice(replies)

        logger.info(
            "Reponse ML commerciale ({}) avec score {:.3f}: '{}' -> '{}' ...",
            best.tag,
            best.score,
            text[:160],
            chosen[:160],
        )
        return chosen

    def build_context(self, text: str, top_k: int = 3) -> Dict[str, Any]:
        """
        Construit un contexte ML exploitable par l'agenda.

        Ce contexte est utile meme si la reponse vocale ML est desactivee,
        car il permet d'exposer les intents probables + confiance.
        """
        normalized_text = (text or "").strip()
        if not normalized_text:
            return {
                "ml_enabled": self.enabled,
                "threshold": self.threshold,
                "input_text": "",
                "top_predictions": [],
                "best_intent": None,
                "best_score": 0.0,
                "is_confident": False,
                "candidate_responses": [],
            }

        preds = self.predictor.predict(normalized_text, top_k=max(1, top_k))
        top_predictions = [{"tag": item.tag, "score": round(float(item.score), 4)} for item in preds]
        best = preds[0] if preds else None
        candidate_responses = self.store.get_responses_for_tag(best.tag) if best else []

        return {
            "ml_enabled": self.enabled,
            "threshold": self.threshold,
            "input_text": normalized_text,
            "top_predictions": top_predictions,
            "best_intent": best.tag if best else None,
            "best_score": round(float(best.score), 4) if best else 0.0,
            "is_confident": bool(best and best.score >= self.threshold),
            "candidate_responses": candidate_responses[:5],
        }
