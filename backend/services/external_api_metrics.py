"""
Compteur léger des requêtes API externes (fenêtre glissante 60s).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Any, Dict, Deque, Tuple


@dataclass
class _Sample:
    ts: float
    provider: str
    ok: bool


class ExternalApiMetrics:
    def __init__(self, window_seconds: int = 60) -> None:
        self.window_seconds = window_seconds
        self._lock = Lock()
        self._samples: Deque[_Sample] = deque()

    def record(self, provider: str, ok: bool) -> None:
        now = monotonic()
        with self._lock:
            self._samples.append(_Sample(ts=now, provider=provider, ok=ok))
            self._prune_locked(now)

    def snapshot(self) -> Dict[str, Any]:
        now = monotonic()
        with self._lock:
            self._prune_locked(now)
            per_provider: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "ok": 0, "errors": 0})
            for s in self._samples:
                row = per_provider[s.provider]
                row["total"] += 1
                if s.ok:
                    row["ok"] += 1
                else:
                    row["errors"] += 1
            total = sum(v["total"] for v in per_provider.values())
            return {
                "window_seconds": self.window_seconds,
                "total_per_minute": total,
                "providers": dict(sorted(per_provider.items(), key=lambda kv: kv[0])),
            }

    def _prune_locked(self, now: float) -> None:
        cutoff = now - float(self.window_seconds)
        while self._samples and self._samples[0].ts < cutoff:
            self._samples.popleft()


external_api_metrics = ExternalApiMetrics(window_seconds=60)
