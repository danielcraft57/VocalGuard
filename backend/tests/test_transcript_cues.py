"""Tests des cues SRT 4-5 mots pour l'UI karaoke."""

from backend.voice.transcript_cues import build_transcript_cues, chunk_words, split_words


def test_chunk_words_groups_four_to_five() -> None:
    """Les mots sont regroupes par paquets de 5, dernier mot isole fusionne."""
    words = [f"m{i}" for i in range(11)]
    groups = chunk_words(words)
    assert [len(g) for g in groups] == [5, 6]


def test_build_cues_from_plain_text() -> None:
    """Sans segments Whisper, le temps est etale sur toute la duree."""
    text = "Bonjour monsieur Daniel ici l entreprise Chia Bada merci"
    cues = build_transcript_cues(text, duration_sec=10.0)
    assert len(cues) >= 2
    assert all(4 <= len(c["words"]) <= 6 for c in cues)
    assert cues[0]["start"] == 0.0
    assert cues[-1]["end"] == 10.0
    assert split_words(text)[0] == cues[0]["words"][0]["text"]


def test_build_cues_prefers_whisper_segments() -> None:
    """Les timestamps Whisper segmentent le karaoke."""
    cues = build_transcript_cues(
        "ignored",
        duration_sec=99.0,
        segments=[
            {"start": 1.0, "end": 3.0, "text": "un deux trois quatre cinq"},
            {"start": 4.0, "end": 5.0, "text": "six sept huit neuf"},
        ],
    )
    assert len(cues) == 2
    assert cues[0]["start"] == 1.0
    assert cues[0]["end"] == 3.0
    assert cues[1]["start"] == 4.0
    assert [w["text"] for w in cues[1]["words"]] == ["six", "sept", "huit", "neuf"]
