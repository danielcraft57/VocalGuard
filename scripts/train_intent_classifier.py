#!/usr/bin/env python3
"""
Construit et sauvegarde un modele ML d intents depuis les JSON DanielCraft.

Par defaut, l'entrainement cible le **flux sortant** (`outbound`) pour coller au scénario
`prospection-outbound`. On peut basculer vers `inbound` ou `all` via `--profile`.

Sortie principale :
  models/intent_classifier.pkl

Dependances Python : scikit-learn, joblib
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections import Counter
from typing import List, Sequence, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.pipeline import Pipeline

import joblib

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_manifest(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"fichier JSON introuvable: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    intents = payload.get("intents")
    if not isinstance(intents, list):
        raise ValueError("'intents' doit etre une liste")
    cleaned: list[dict[str, object]] = []
    for item in intents:
        if isinstance(item, dict):
            cleaned.append(item)
    return cleaned


def _collect_training_rows(manifest_paths: Sequence[Path]) -> Tuple[List[str], List[str]]:
    texts: List[str] = []
    labels: List[str] = []
    occurrences_per_tag: dict[str, int] = {}

    for manifest_path in manifest_paths:
        intents = _load_manifest(manifest_path)

        # Simple augmentation analogue a JsonMarketingIntentStore.augment_training_examples mais localisée ici
        fillers = ["", "oui ", "hum ", "pour info "]
        suffixes = ["", " ?", " alors", " s il vous plait"]

        for intent in intents:
            tag = intent.get("tag")
            patterns = intent.get("patterns") or []
            tag_str = str(tag or "").strip()
            if not tag_str:
                continue

            originals: list[str] = []
            for pattern in patterns:
                p_clean = str(pattern).strip().lower()
                if len(p_clean) < 2:
                    continue
                originals.append(p_clean)

            augmented: list[str] = []
            augmented.extend(originals)

            for base in originals:
                augmented.append(base + "." if not base.endswith(".") else base)
                for filler in fillers:
                    if filler:
                        augmented.append((filler + base).strip())
                for suffix in suffixes:
                    if suffix:
                        augmented.append((base + suffix).strip())

                if (
                    tag_str.startswith("n4_marketing")
                    or tag_str.startswith("offer_")
                    or tag_str.startswith("objection_")
                ):
                    augmented.extend(
                        [
                            "je vous appelle pour discuter : " + base,
                            "petite precision : " + base,
                            "question courte : " + base,
                        ]
                    )

            seen = set()
            for phrase in augmented:
                key = phrase.strip().lower()
                if len(key) < 2 or key in seen:
                    continue
                seen.add(key)
                texts.append(key)
                labels.append(tag_str)
                occurrences_per_tag[tag_str] = occurrences_per_tag.get(tag_str, 0) + 1

    total = len(labels)
    if total == 0:
        raise RuntimeError("Jeux d entraînement vide: vérifiez vos fichiers intents JSON.")

    uniq_labels = sorted(set(labels))
    print(f"Jeux créé avec {total} lignes étiquettées parmi {len(uniq_labels)} tags.")
    small_tags = sorted([lbl for lbl, cnt in occurrences_per_tag.items() if cnt < 3])
    if small_tags[:10]:
        print(
            "Attention: certains tags ont très peu d exemples:",
            ",".join(small_tags[:20]),
            file=sys.stderr,
        )

    return texts, labels


def _tag_family(tag: str) -> str:
    t = (tag or "").strip().lower()
    if not t:
        return "unknown"
    if t.startswith("in_n"):
        # Ex: in_n2_budget_investissement -> in_n2
        parts = t.split("_")
        if len(parts) >= 2:
            return "_".join(parts[:2])
        return "inbound"
    if t.startswith("n") and len(t) >= 2 and t[1].isdigit():
        # Ex: n3_followup_commitment -> n3
        return t.split("_", 1)[0]
    return t.split("_", 1)[0]


def _resolve_profile_glob(profile: str) -> str:
    p = (profile or "").strip().lower()
    if p == "outbound":
        return "data/intents/danielcraft/outbound/**/*.json"
    if p == "inbound":
        return "data/intents/danielcraft/inbound/**/*.json"
    return "data/intents/danielcraft/**/*.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Entraîne le classifieur d intents ML DanielCraft.")
    parser.add_argument(
        "--profile",
        choices=["outbound", "inbound", "all"],
        default="outbound",
        help="Sous-ensemble DanielCraft à entraîner (défaut: outbound).",
    )
    parser.add_argument(
        "--glob",
        dest="glob_pattern",
        default=None,
        help="Motif glob explicite depuis la racine (prioritaire sur --profile).",
    )
    parser.add_argument(
        "--out",
        dest="output_path",
        default=str(PROJECT_ROOT / "models" / "intent_classifier.pkl"),
        help="Chemin fichier .pkl de sortie (joblib sklearn).",
    )
    parser.add_argument(
        "--test-size",
        dest="test_size",
        type=float,
        default=0.2,
        help="Pourcentage de validation (stratifie). Mettre a 0 pour tout utiliser comme entrainement.",
    )

    args = parser.parse_args()

    glob_pattern = str(args.glob_pattern).strip() if args.glob_pattern else _resolve_profile_glob(args.profile)
    matches = sorted(PROJECT_ROOT.glob(glob_pattern))
    if not matches:
        raise SystemExit(f"Aucun fichier ne correspond au motif {glob_pattern}")

    print(f"Profil intents: {args.profile}")
    print(f"Glob utilisé: {glob_pattern}")
    print("Fichiers JSON utilisés:")
    for m in matches:
        print(f" - {m.relative_to(PROJECT_ROOT)}")

    texts, labels = _collect_training_rows(matches)
    families = Counter(_tag_family(lbl) for lbl in labels)
    print("Répartition par famille de tags:")
    for fam, cnt in sorted(families.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f" - {fam}: {cnt}")

    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 5),
        min_df=1,
        sublinear_tf=True,
    )

    # Note: suivant votre version sklearn, multi_class peut ne plus exister; le comportement par défaut gère plusieurs classes correctement avec lbfgs.
    clf = LogisticRegression(max_iter=2000, solver="lbfgs")

    pipeline = Pipeline(
        [
            ("tfidf", vectorizer),
            ("clf", clf),
        ]
    )

    if args.test_size > 0 and len(labels) >= 12:
        splitter = StratifiedShuffleSplit(
            n_splits=1,
            test_size=args.test_size,
            random_state=42,
        )
        indices = next(splitter.split(texts, labels))
        train_idx, test_idx = indices
        X_train = [texts[i] for i in train_idx]
        y_train = [labels[i] for i in train_idx]
        X_test = [texts[i] for i in test_idx]
        y_test = [labels[i] for i in test_idx]

        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)
        report = classification_report(y_test, y_pred, digits=3, zero_division=0)
        print("Rapport de validation:")
        print(report)
    else:
        pipeline.fit(texts, labels)
        print("Mode entièrement supervise (pas assez de lignes pour split automatique réaliste).")

    out_path = Path(args.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, out_path)

    print(f"Modèle sklearn sauvegardé : {out_path}")


def _safe_main() -> None:
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    _safe_main()
