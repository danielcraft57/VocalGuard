"""Tests unitaires pour ``labcore.scenario_bookmarks`` et la résolution ``cli``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

LAB_DIR = Path(__file__).resolve().parents[1]
if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))

from labcore import scenario_bookmarks as sb
from labcore.scenario_bookmarks import (
    load_bookmarks,
    merge_bookmark_and_user_args,
    resolve_run,
    save_bookmarks,
    validate_bookmark_id,
)


def test_validate_reserved_builtin_name() -> None:
    builtins = {"dialer", "smoke"}
    assert validate_bookmark_id("dialer", builtins) is not None
    assert validate_bookmark_id("smoke", builtins) is not None


def test_validate_ok_id() -> None:
    assert validate_bookmark_id("mon-raccourci", {"dialer"}) is None
    assert validate_bookmark_id("x", {"dialer"}) is None


def test_validate_invalid_syntax() -> None:
    assert validate_bookmark_id("", {"dialer"}) is not None
    assert validate_bookmark_id("9bad", {"dialer"}) is not None


def test_merge_bookmark_and_user_args() -> None:
    assert merge_bookmark_and_user_args(["--hold-seconds", "3"], ["--port", "COM1"]) == [
        "--hold-seconds",
        "3",
        "--port",
        "COM1",
    ]
    assert merge_bookmark_and_user_args([], ["--", "--x", "1"]) == ["--x", "1"]


def test_resolve_builtin() -> None:
    import cli as modem_lab_cli

    r = resolve_run("smoke", scenario_map=modem_lab_cli.SCENARIO_MAP, bookmarks={})
    assert r is not None
    script, prefix = r
    assert script.name == "smoke_tests.py"
    assert prefix == []


def test_resolve_bookmark() -> None:
    import cli as modem_lab_cli

    marks = {
        "court": {
            "scenario": "dialer",
            "args": ["--hold-seconds", "2"],
            "description": "test",
        }
    }
    r = resolve_run("court", scenario_map=modem_lab_cli.SCENARIO_MAP, bookmarks=marks)
    assert r is not None
    script, prefix = r
    assert script.name == "dialer.py"
    assert prefix == ["--hold-seconds", "2"]


def test_load_save_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Évite ``tmp_path`` (pytest sous Windows) : fichier sous ``generated/`` ignoré par git."""
    d = LAB_DIR / "generated" / "_pytest_bookmark_rw"
    d.mkdir(parents=True, exist_ok=True)
    bf = d / "scenario_bookmarks.json"
    monkeypatch.setattr(sb, "bookmarks_file", lambda _lab: bf)
    try:
        save_bookmarks(
            d,
            {
                "a": {"scenario": "smoke", "args": ["--x", "1"], "description": "d"},
            },
        )
        got = load_bookmarks(d)
        assert got["a"]["scenario"] == "smoke"
        assert got["a"]["args"] == ["--x", "1"]
        assert got["a"]["description"] == "d"
        raw = json.loads(bf.read_text(encoding="utf-8"))
        assert raw["version"] == 1
        assert "a" in raw["bookmarks"]
    finally:
        try:
            bf.unlink(missing_ok=True)
        except OSError:
            pass
