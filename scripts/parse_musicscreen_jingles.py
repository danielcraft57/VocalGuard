#!/usr/bin/env python3
"""Parse la page MusicScreen jingles et ecrit catalog.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "tmp_musicscreen.html"
OUT_DIR = ROOT / "resources" / "voice" / "jingles"
CATALOG = OUT_DIR / "catalog.json"


def main() -> None:
    html = HTML.read_text(encoding="latin-1", errors="replace")
    entries: list[dict] = []
    for block in re.split(r"<hr><br>", html):
        m_url = re.search(
            r"src=(https://www\.musicscreen\.be/mp3gallery/content/songs/MP3/Jingles/[^\s>]+\.mp3)",
            block,
        )
        if not m_url:
            continue
        url = m_url.group(1)
        m_title = re.search(r"Catalogue/([^\"]+)-Jingle\.html", block)
        title = m_title.group(1).replace("-", " ") if m_title else Path(url).stem.replace("-Jingle", "")
        m_dur = re.search(r"Durée:\s*(\d+):(\d+)", block)
        dur = int(m_dur.group(1)) * 60 + int(m_dur.group(2)) if m_dur else None
        fid = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
        entries.append(
            {
                "id": fid,
                "label": title.strip(),
                "url": url,
                "duration_sec": dur,
                "filename": Path(url).name,
            }
        )
    seen: set[str] = set()
    out: list[dict] = []
    for entry in entries:
        if entry["id"] in seen:
            continue
        seen.add(entry["id"])
        out.append(entry)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"catalog: {len(out)} jingles -> {CATALOG}")


if __name__ == "__main__":
    main()
