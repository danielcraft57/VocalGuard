#!/usr/bin/env python3
"""Telecharge les MP3 jingles MusicScreen listes dans catalog.json."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "resources" / "voice" / "jingles" / "catalog.json"
OUT_DIR = ROOT / "resources" / "voice" / "jingles"


def main() -> None:
    items = json.loads(CATALOG.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for item in items:
        dest = OUT_DIR / item["filename"]
        if dest.is_file() and dest.stat().st_size > 1000:
            ok += 1
            continue
        print("GET", item["filename"])
        urllib.request.urlretrieve(item["url"], dest)
        ok += 1
    print(f"ok {ok}/{len(items)}")


if __name__ == "__main__":
    main()
