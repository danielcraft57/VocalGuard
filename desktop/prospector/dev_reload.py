"""
Rechargement a chaud en dev : redemarre le process Prospector quand des .py changent.

Pas d'import dynamique du module Qt (trop fragile) — on relance ``python -m desktop.prospector``.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Evite import circulaire avec settings : racine repo comme dans prospector/settings.py


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def is_hot_reload_parent() -> bool:
    """
    True si ce process doit surveiller les fichiers et relancer l'enfant.

    Active avec ``VG_PROSPECTOR_HOT_RELOAD=1`` ; l'enfant porte ``VG_PROSPECTOR_DEV_CHILD=1``.
    """
    return _truthy("VG_PROSPECTOR_HOT_RELOAD") and not _truthy("VG_PROSPECTOR_DEV_CHILD")


def watch_directories() -> List[Path]:
    """
    Dossiers a surveiller (recursif, fichiers ``*.py``).

    Defaut : ``desktop/`` et ``backend/core/``. Surcharge :
    ``VG_PROSPECTOR_HOT_RELOAD_PATHS`` avec chemins separes par ``;`` (Windows) ou ``:``.
    """
    root = _repo_root()
    raw = (os.environ.get("VG_PROSPECTOR_HOT_RELOAD_PATHS") or "").strip()
    if raw:
        sep = ";" if ";" in raw else ":"
        out: List[Path] = []
        for part in raw.split(sep):
            p = Path(part.strip())
            if not p.is_absolute():
                p = root / p
            if p.is_dir():
                out.append(p)
        return out if out else [root / "desktop", root / "backend" / "core"]
    return [root / "desktop", root / "backend" / "core"]


def _snapshot_py_mtimes() -> Dict[Path, float]:
    """Mtime par fichier .py sous les repertoires configures."""
    snap: Dict[Path, float] = {}
    for base in watch_directories():
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            try:
                snap[p.resolve()] = p.stat().st_mtime
            except OSError:
                continue
    return snap


def _build_child_env() -> dict:
    env = os.environ.copy()
    env["VG_PROSPECTOR_DEV_CHILD"] = "1"
    env.pop("VG_PROSPECTOR_HOT_RELOAD", None)
    return env


def _spawn_child() -> subprocess.Popen:
    """
    Lance le meme interpreteur avec ``-m desktop.prospector`` et les memes args.

    Sous Windows, ``CREATE_NEW_PROCESS_GROUP`` evite que Ctrl+C du terminal tue
    brutalement l'enfant Qt : seul le parent recoit SIGINT et peut arreter l'enfant
    proprement (terminate/kill).
    """
    cmd = [sys.executable, "-m", "desktop.prospector", *sys.argv[1:]]
    kw: dict = {"cwd": str(_repo_root()), "env": _build_child_env()}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(cmd, **kw)


def run_hot_reload_parent() -> int:
    """
    Boucle parent : tue et relance l'enfant quand un ``.py`` surveille change.

    Ctrl+C (SIGINT) ou arret propre : termine l'enfant puis quitte.

    @returns Code sortie du dernier enfant.
    """
    if str(_repo_root()) not in sys.path:
        sys.path.insert(0, str(_repo_root()))

    poll = float(os.environ.get("VG_PROSPECTOR_HOT_RELOAD_POLL", "0.7") or "0.7")
    last = _snapshot_py_mtimes()
    proc_holder: List[Optional[subprocess.Popen]] = [_spawn_child()]

    def _stop_child() -> None:
        proc = proc_holder[0]
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=4.0)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=2.0)
            except Exception:
                pass

    def _on_exit_sig(_signum: int, _frame) -> None:  # type: ignore[no-untyped-def]
        _stop_child()
        sys.exit(130)

    # Ctrl+C : arret net sans traceback KeyboardInterrupt encombrant
    signal.signal(signal.SIGINT, _on_exit_sig)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _on_exit_sig)
    if sys.platform == "win32" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _on_exit_sig)

    try:
        while True:
            step = min(0.2, poll)
            elapsed = 0.0
            while elapsed < poll:
                time.sleep(step)
                elapsed += step
                if proc_holder[0] is not None and proc_holder[0].poll() is not None:
                    return int(proc_holder[0].returncode or 0)
            proc = proc_holder[0]
            if proc is not None and proc.poll() is not None:
                return int(proc.returncode or 0)
            cur = _snapshot_py_mtimes()
            if cur != last:
                last = cur
                _stop_child()
                proc_holder[0] = _spawn_child()
    except KeyboardInterrupt:
        _stop_child()
        return 130


__all__ = ["is_hot_reload_parent", "run_hot_reload_parent", "watch_directories"]
