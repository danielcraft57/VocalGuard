"""
Applique les migrations Alembic Prospector au demarrage.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from desktop.prospector.settings import bundle_root, load_prospector_env


def alembic_ini_path() -> Path:
    """Chemin alembic.ini Prospector (dev ou bundle PyInstaller)."""
    if getattr(sys, "frozen", False):
        return bundle_root() / "desktop" / "prospector" / "alembic.ini"
    return Path(__file__).resolve().parents[1] / "alembic.ini"


def upgrade_head() -> None:
    """
    Execute alembic upgrade head sur la base configuree.

    @returns None
    """
    load_prospector_env()
    root = bundle_root()
    os.chdir(root)
    ini = alembic_ini_path()
    if not ini.is_file():
        raise FileNotFoundError(f"alembic.ini introuvable: {ini}")
    cfg = Config(str(ini))
    if getattr(sys, "frozen", False):
        script = root / "desktop" / "prospector" / "alembic"
        cfg.set_main_option("script_location", str(script))
    command.upgrade(cfg, "head")
