#!/usr/bin/env python3
"""
Regenere beep, blocked_short et jingles intro au format modem USR (11 kHz 16-bit).

Usage prod (node14) :
  /opt/vocalguard/venv/bin/python /tmp/refresh_modem_voice_assets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/opt/vocalguard")
if not ROOT.is_dir():
    ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))

from backend.core.config import Config
from backend.core.incoming_call_audio import refresh_modem_voice_assets
from backend.core.incoming_call_settings import load_incoming_call_settings


def main() -> None:
    config = Config()
    config.base_path = str(ROOT)
    settings = load_incoming_call_settings(config)
    paths = refresh_modem_voice_assets(config, settings)
    print("ok", len(paths))
    for rel in paths:
        print(rel)


if __name__ == "__main__":
    main()
