"""
Tests unitaires moteur commercial sortant + ElevenLabs (sans reseau).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.voice.elevenlabs_tts import ElevenLabsTts, PREVIEW_MAX_CHARS
from backend.voice.qdrant_intents import (
    COLLECTION_INBOUND,
    COLLECTION_OUTBOUND_COMMERCIAL,
    collection_for_profile,
)
from backend.voice.response_picker import variant_wav_basename


def test_collection_for_profile() -> None:
    """Profils KB mappent vers les bonnes collections Qdrant."""
    assert collection_for_profile("inbound") == COLLECTION_INBOUND
    assert collection_for_profile("outbound_commercial") == COLLECTION_OUTBOUND_COMMERCIAL
    assert collection_for_profile(None) == COLLECTION_INBOUND


def test_variant_wav_basename_outbound() -> None:
    """Variantes out_kb_* correctes."""
    assert variant_wav_basename("out_presentation", 0, wav_basename="out_kb_out_presentation") == (
        "out_kb_out_presentation"
    )
    assert variant_wav_basename("out_presentation", 2, wav_basename="out_kb_out_presentation") == (
        "out_kb_out_presentation_r2"
    )


def test_elevenlabs_cache_key_stable() -> None:
    """Meme texte + voix => meme cle cache."""
    cache = Path("audio_cache") / "_test_elevenlabs"
    cache.mkdir(parents=True, exist_ok=True)
    client = ElevenLabsTts(
        api_key="test-key",
        voice_id="voiceA",
        model_id="modelB",
        cache_dir=cache,
    )
    a = client.cache_key("Bonjour")
    b = client.cache_key("Bonjour")
    c = client.cache_key("Autre")
    assert a == b
    assert a != c


def test_elevenlabs_preview_truncate_constant() -> None:
    """Limite apercu pour economiser le quota."""
    assert PREVIEW_MAX_CHARS <= 120


def test_outbound_seed_file_exists() -> None:
    """Seed commercial present et parseable."""
    import json

    path = Path("data/intents/kb_seed/outbound_commercial_v1.json")
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    intents = payload.get("intents") or []
    assert len(intents) >= 10
    for item in intents:
        assert item.get("profile") == "outbound_commercial"
        assert len(item.get("responses") or []) == 5
        assert str(item.get("wav_basename") or "").startswith("out_kb_")
