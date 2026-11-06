"""
Applique les migrations Alembic Prospector au demarrage.
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from desktop.prospector.settings import load_prospector_env


def alembic_ini_path() -> Path:
    """Chemin alembic.ini Prospector."""
    return Path(__file__).resolve().parents[1] / "alembic.ini"


def upgrade_head() -> None:
    """
    Execute alembic upgrade head sur la base configuree.

    @returns None
    """
    root = Path(__file__).resolve().parents[3]
    os.chdir(root)
    load_prospector_env()
    cfg = Config(str(alembic_ini_path()))
    command.upgrade(cfg, "head")
