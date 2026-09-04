"""
Tests prefetch TTS intents (skip si WAV fresh).
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base
from backend.services import intent_repository as intent_repo
from backend.services.kb_tts_prefetch import prefetch_intent_voices


@pytest.mark.asyncio
async def test_prefetch_skips_fresh(tmp_path: Path):
    """Si cache fresh → skipped."""
    engine = create_engine(f"sqlite:///{tmp_path / 'p.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    root = Path(__file__).resolve().parents[2]
    catalog = intent_repo.load_seed_catalog(
        root / "data" / "intents" / "kb_seed" / "conversation_v1.json"
    )
    # Un seul intent pour aller vite
    catalog = [c for c in catalog if c["tag"] == "remerciements"]
    intent_repo.seed_intents_from_catalog(db, catalog, replace=True)

    config = MagicMock()
    config.base_path = tmp_path
    config.edge_tts_voice = "fr-FR-DeniseNeural"
    config.edge_tts_rate = "+0%"
    config.edge_tts_pitch = "+0Hz"
    config.edge_tts_voice_gain_db = -6.0
    config.stt_service_url = None
    config.tts_service_url = None
    config.voice_sample_rate = 8000
    config.voice_sample_width = 1

    synthesis = MagicMock()
    synthesis.engine = "edge"

    # Pre-marque fresh
    from backend.voice.ivr_cache import IvrAudioCache

    cache = IvrAudioCache(config, synthesis)
    text = catalog[0]["responses"][0]
    basename = "kb_remerciements"
    (tmp_path / "ivr_wav").mkdir(parents=True, exist_ok=True)
    wav = tmp_path / "ivr_wav" / f"{basename}.wav"
    wav.write_bytes(b"RIFF....")
    meta = tmp_path / "ivr_wav" / f"{basename}.meta.json"
    meta.write_text(
        __import__("json").dumps({"hash": cache._current_hash(text), "text": text}),
        encoding="utf-8",
    )

    result = await prefetch_intent_voices(db, config, synthesis, force=False, tags=["remerciements"])
    assert result["skipped"] >= 1
    assert result["ok"] == 0
    db.close()
