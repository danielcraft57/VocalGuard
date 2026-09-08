"""
Accumulateur de croyance d'intents (EMA + seuil de commit).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple


@dataclass
class BeliefConfig:
    """
    Parametres de fusion et de commit precoce.

    @param alpha Poids du score courant dans l'EMA (0..1).
    @param commit_threshold Score min du max pour commit.
    @param commit_margin Ecart min entre 1er et 2e.
    @param min_speech_ms Duree mini de parole avant commit precoce.
    @param min_chunks Nombre mini de mises a jour avant commit precoce.
    @param strong_threshold Score tres haut : commit des le 1er chunk.
    @param strong_margin Marge 1er/2e pour commit 1-chunk.
    @param strong_min_speech_ms Parole mini pour commit 1-chunk.
    @param fallback_tag Tag si score trop bas a la fin du tour.
    @param low_threshold Sous ce max, on tombe en fallback a la fin.
    """

    alpha: float = 0.55
    commit_threshold: float = 0.68
    commit_margin: float = 0.12
    min_speech_ms: float = 500.0
    min_chunks: int = 2
    strong_threshold: float = 0.82
    strong_margin: float = 0.22
    strong_min_speech_ms: float = 350.0
    fallback_tag: str = "incompris"
    low_threshold: float = 0.35


@dataclass
class BeliefState:
    """Etat d'un tour de conversation."""

    belief: Dict[str, float] = field(default_factory=dict)
    chunks: int = 0
    speech_ms: float = 0.0
    committed_tag: Optional[str] = None


class IntentBeliefAccumulator:
    """
    Affine une distribution d'intents chunk apres chunk.

    @example
        acc = IntentBeliefAccumulator()
        acc.update({"prise_rdv": 0.4, "salutation": 0.3}, speech_ms=400)
        decided = acc.try_commit()
    """

    def __init__(self, config: Optional[BeliefConfig] = None) -> None:
        """
        @param config Seuils ; defauts du plan latence.
        """
        self.config = config or BeliefConfig()
        self.state = BeliefState()

    def reset(self) -> None:
        """Remet a zero l'etat pour le tour suivant."""
        self.state = BeliefState()

    def update(
        self,
        scores: Mapping[str, float],
        *,
        speech_ms: float = 0.0,
        pattern_boost: Optional[Mapping[str, float]] = None,
    ) -> Dict[str, float]:
        """
        Fusionne les scores d'un predict (texte cumule) dans la belief.

        @param scores Scores bruts tag -> [0..1] (ou non normalises).
        @param speech_ms Duree de parole ajoutee depuis le dernier update.
        @param pattern_boost Boost optionnel keywords (ajoute avant EMA).
        @returns Distribution renormalisee courante.
        """
        cfg = self.config
        merged: Dict[str, float] = {k: float(v) for k, v in scores.items() if v is not None}
        if pattern_boost:
            for tag, bonus in pattern_boost.items():
                merged[tag] = merged.get(tag, 0.0) + float(bonus)
        if not merged:
            return dict(self.state.belief)

        # Initialise les tags manquants a 0.
        for tag in merged:
            if tag not in self.state.belief:
                self.state.belief[tag] = 0.0
        for tag in list(self.state.belief.keys()):
            if tag not in merged:
                merged[tag] = 0.0

        alpha = max(0.0, min(1.0, float(cfg.alpha)))
        for tag, score in merged.items():
            prev = self.state.belief.get(tag, 0.0)
            self.state.belief[tag] = (1.0 - alpha) * prev + alpha * float(score)

        self._renormalize()
        self.state.chunks += 1
        self.state.speech_ms += max(0.0, float(speech_ms))
        return dict(self.state.belief)

    def _renormalize(self) -> None:
        """Force la somme des beliefs a 1 (si > 0)."""
        total = sum(max(0.0, v) for v in self.state.belief.values())
        if total <= 1e-12:
            return
        self.state.belief = {k: max(0.0, v) / total for k, v in self.state.belief.items()}

    def ranking(self, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Classement des tags par score decroissant.

        @param top_k Nombre max d'entrees.
        @returns Liste (tag, score).
        """
        items = sorted(self.state.belief.items(), key=lambda kv: kv[1], reverse=True)
        return items[: max(1, int(top_k))]

    def try_commit(self, *, force: bool = False) -> Optional[str]:
        """
        Decide si on commit un intent.

        @param force True = fin de tour (silence) : commit max ou fallback.
        @returns Tag committe ou None si on continue a ecouter.
        """
        if self.state.committed_tag:
            return self.state.committed_tag
        ranking = self.ranking(top_k=2)
        if not ranking:
            if force:
                self.state.committed_tag = self.config.fallback_tag
                return self.state.committed_tag
            return None

        best_tag, best_score = ranking[0]
        second = ranking[1][1] if len(ranking) > 1 else 0.0
        margin = best_score - second
        cfg = self.config

        if force:
            if best_score < cfg.low_threshold:
                self.state.committed_tag = cfg.fallback_tag
            else:
                self.state.committed_tag = best_tag
            return self.state.committed_tag

        # Commit 1-chunk si l'intent est deja tres clair (latence).
        if (
            self.state.chunks >= 1
            and self.state.speech_ms >= cfg.strong_min_speech_ms
            and best_score >= cfg.strong_threshold
            and margin >= cfg.strong_margin
        ):
            self.state.committed_tag = best_tag
            return best_tag

        ready = (
            self.state.chunks >= cfg.min_chunks
            and self.state.speech_ms >= cfg.min_speech_ms
        )
        if (
            ready
            and best_score >= cfg.commit_threshold
            and margin >= cfg.commit_margin
        ):
            self.state.committed_tag = best_tag
            return best_tag
        return None

    def as_event_payload(self, *, call_id: Optional[int] = None) -> Dict[str, object]:
        """
        Payload WS pour barres de proba live.

        @param call_id ID appel courant.
        @returns Dict serialisable.
        """
        return {
            "call_id": call_id,
            "belief": dict(self.state.belief),
            "top": [{"tag": t, "score": s} for t, s in self.ranking(5)],
            "chunks": self.state.chunks,
            "speech_ms": self.state.speech_ms,
            "committed_tag": self.state.committed_tag,
        }
