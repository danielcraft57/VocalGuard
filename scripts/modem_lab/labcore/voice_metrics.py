#!/usr/bin/env python3
"""
Outils de collecte et persistance des métriques voix.

Ce module centralise:
- le schéma de colonnes CSV pour les métriques de détection
- une écriture synchrone simple (liste de lignes)
- un writer CSV en thread (queue + flush) pour les captures longues
"""

from __future__ import annotations

import csv
import queue
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from loguru import logger

METRICS_HEADERS: list[str] = [
    "kind",
    "t_sec",
    "cd",
    "raw_score",
    "raw_jitter",
    "raw_zcr",
    "raw_periodicity",
    "score_span",
    "jitter_span",
    "active_ms",
    "voice_gate_open",
]


def _normalize_row(row: dict[str, Any], headers: list[str]) -> dict[str, Any]:
    return {k: row.get(k, "") for k in headers}


def write_metrics_csv(path: Path, rows: Iterable[dict[str, Any]], headers: list[str] | None = None) -> None:
    """Écriture synchrone d'un CSV métriques."""
    cols = headers or METRICS_HEADERS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in rows:
            w.writerow(_normalize_row(row, cols))


class MetricsCsvThreadWriter:
    """
    Writer CSV asynchrone par thread.

    Usage:
    - start() au début de la capture
    - push(row) pour chaque métrique
    - close() en fin de capture
    """

    def __init__(
        self,
        out_path: Path,
        *,
        headers: list[str] | None = None,
        flush_interval_sec: float = 0.5,
        max_queue_size: int = 4096,
        daemon: bool = True,
    ) -> None:
        self._path = Path(out_path)
        self._headers = headers or METRICS_HEADERS
        self._flush_interval_sec = max(0.1, float(flush_interval_sec))
        self._q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=max_queue_size)
        self._stop = threading.Event()
        self._started = False
        self._dropped = 0
        self._thread = threading.Thread(target=self._run, name="voice-metrics-writer", daemon=daemon)

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def push(self, row: dict[str, Any]) -> None:
        if not self._started:
            self.start()
        try:
            self._q.put_nowait(row)
        except queue.Full:
            self._dropped += 1

    def close(self, timeout: float = 5.0) -> None:
        if not self._started:
            return
        self._stop.set()
        self._thread.join(timeout=max(0.5, float(timeout)))
        if self._thread.is_alive():
            logger.warning("voice_metrics: arrêt writer thread incomplet (timeout)")
        if self._dropped:
            logger.warning("voice_metrics: {} lignes métriques perdues (queue pleine)", self._dropped)

    def _run(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self._headers)
            w.writeheader()
            last_flush = time.monotonic()
            while not self._stop.is_set() or not self._q.empty():
                try:
                    row = self._q.get(timeout=0.1)
                    w.writerow(_normalize_row(row, self._headers))
                except queue.Empty:
                    pass
                now = time.monotonic()
                if now - last_flush >= self._flush_interval_sec:
                    f.flush()
                    last_flush = now
            f.flush()
