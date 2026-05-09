"""
**Chaîne de responsabilité** sur les intentions (fichiers JSON + ordre interne).

Chaque fichier JSON est un « maillon » : on parcourt les fichiers **dans l’ordre**
donné par ``ProspectionDialogueConfig.intent_json_paths``. Dans chaque fichier,
on parcourt les entrées ``intents`` **dans l’ordre du tableau** : la première
intention dont un **pattern** est une sous-chaîne de la transcription **et**
pour laquelle un WAV existe sur disque **porte** la décision.

La variante WAV (``_01``, ``_02``, …) est choisie **au hasard** parmi les fichiers
réellement présents (stratégie A/B pour les réponses multiples).

Implémente le port ``IntentMatcherProtocol`` (``ports.py``) : le scénario dépend de cette
interface, pas de la classe concrète, pour faciliter tests et évolutions (fuzzy match, etc.).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labaudio.intent_wav_pack import list_intent_variants_on_disk


@dataclass(frozen=True)
class IntentMatchResult:
    """
    Résultat d’un matching réussi (un seul intent « gagnant » par tour).

    Attributes
    ----------
    wav_path:
        Fichier audio à jouer sur la ligne.
    intent_tag:
        Champ ``tag`` du JSON (identifiant stable, ex. ``n1_anti_spam_reassurance``).
    variant_index:
        Indice 1-based de la variante choisie (aligné sur le suffixe ``_01.wav``).
    pattern_matched:
        Motif ``patterns`` qui a déclenché le match (debug / logs).
    source_json:
        Fichier JSON d’où provient l’intent (traçabilité de la chaîne).
    terminal:
        ``True`` si ``intent_tag`` appartient aux tags terminaux de la config.
    """

    wav_path: Path
    intent_tag: str
    variant_index: int
    pattern_matched: str
    source_json: Path
    terminal: bool


class IntentChain:
    """
    Chaîne : plusieurs fichiers JSON chargés une fois à l’instanciation.

    Parameters
    ----------
    intent_json_paths:
        Ordre = priorité métier (ex. fichier « stop / RGPD » avant fichier « niveau 1 »).
    terminal_tags:
        Ensemble de tags qui imposent d’arrêter le dialogue après lecture.
    """

    def __init__(
        self,
        intent_json_paths: tuple[Path, ...],
        *,
        terminal_tags: frozenset[str],
        _payloads: list[tuple[Path, dict[str, Any]]] | None = None,
    ) -> None:
        self._paths = intent_json_paths
        self._terminal_tags = terminal_tags
        if _payloads is not None:
            self._payloads = list(_payloads)
            return
        self._payloads = []
        for p in self._paths:
            if not p.is_file():
                raise FileNotFoundError(f"Fichier intents introuvable: {p}")
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"JSON intents invalide (racine dict attendu): {p}")
            self._payloads.append((p, data))

    @classmethod
    def from_payloads(
        cls,
        payloads: list[tuple[Path, dict[str, Any]]],
        *,
        terminal_tags: frozenset[str],
    ) -> IntentChain:
        """
        Instanciation sans relecture disque des JSON (chemins + données déjà chargés, ex. cache audio).
        """
        paths = tuple(p for p, _ in payloads)
        return cls(paths, terminal_tags=terminal_tags, _payloads=list(payloads))

    def match(
        self,
        transcript: str,
        pack_dir: Path,
        rng: random.Random,
    ) -> IntentMatchResult | None:
        """
        Trouve au plus une réponse WAV pour la transcription du tour courant.

        :param transcript: texte normalisé en minuscules côté appelant recommandé.
        :param pack_dir: dossier des WAV du pack.
        :param rng: tirage aléatoire des variantes.
        """
        t = (transcript or "").lower().strip()
        if not t:
            return None
        for source_path, payload in self._payloads:
            for item in payload.get("intents") or []:
                tag = str(item.get("tag") or "").strip()
                if not tag:
                    continue
                for pat in item.get("patterns") or []:
                    p = (pat or "").lower().strip()
                    if not p or p not in t:
                        continue
                    variants = list_intent_variants_on_disk(pack_dir, tag)
                    if not variants:
                        continue
                    idx, wav_path = rng.choice(variants)
                    return IntentMatchResult(
                        wav_path=wav_path,
                        intent_tag=tag,
                        variant_index=idx,
                        pattern_matched=str(pat).strip(),
                        source_json=source_path,
                        terminal=tag in self._terminal_tags,
                    )
        return None
