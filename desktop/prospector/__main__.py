"""Point d'entree ``python -m desktop.prospector`` (avec option hot reload)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


if __name__ == "__main__":
    if _truthy("VG_PROSPECTOR_HOT_RELOAD") and not _truthy("VG_PROSPECTOR_DEV_CHILD"):
        from desktop.prospector.dev_reload import run_hot_reload_parent

        raise SystemExit(run_hot_reload_parent())

    from desktop.prospector.app import main

    raise SystemExit(main())
