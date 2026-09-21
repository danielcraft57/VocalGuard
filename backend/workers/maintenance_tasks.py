"""
Taches Celery de maintenance infrastructure VocalGuard (logs, rotation).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from backend.celery_app import celery_app
from backend.core.config import Config

_config = Config()


def _resolve_app_dir() -> Path:
    """
    Resout le repertoire applicatif prod (APP_DIR ou base_path Config).

    @returns Chemin absolu du depot VocalGuard.
    """
    raw = os.environ.get("APP_DIR", "").strip()
    if raw:
        return Path(raw)
    return _config.base_path


@celery_app.task(name="backend.workers.maintenance_tasks.run_log_maintenance")
def run_log_maintenance() -> Dict[str, Any]:
    """
    Lance la maintenance des logs (logrotate + purge archives pre-cleanup).

    Appelee par Celery Beat chaque nuit. Delegue au script shell prod
    pour conserver sudo logrotate et la config logrotate existante.

    @returns Resume d'execution (code retour, chemins, extrait stdout).
    @throws FileNotFoundError Si le script de maintenance est absent.
    """
    app_dir = _resolve_app_dir()
    script = app_dir / "scripts" / "prod_log_maintenance.sh"
    if not script.is_file():
        raise FileNotFoundError(f"Script maintenance logs absent: {script}")

    logger.info("Celery: demarrage maintenance logs ({})", script)
    env = os.environ.copy()
    env["APP_DIR"] = str(app_dir)

    completed = subprocess.run(
        ["bash", str(script)],
        cwd=str(app_dir),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    stdout_tail = (completed.stdout or "").strip()[-2000:]
    stderr_tail = (completed.stderr or "").strip()[-2000:]

    if completed.returncode != 0:
        logger.warning(
            "Maintenance logs rc={} stderr={}",
            completed.returncode,
            stderr_tail or stdout_tail,
        )
    else:
        logger.info("Maintenance logs terminee rc=0")

    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "app_dir": str(app_dir),
        "script": str(script),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }
