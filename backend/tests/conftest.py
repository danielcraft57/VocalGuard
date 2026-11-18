"""
Fixtures partagees (evite tmp Windows systeme souvent verrouille).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest


@pytest.fixture
def isolated_work_dir(monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Repertoire de travail sous data/pytest_workspace (projet).

    @param monkeypatch Fixture pytest chdir.
    @returns Chemin absolu cree pour le test.
    """
    base = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "pytest_workspace"
        / uuid.uuid4().hex
    )
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(base)
    return base