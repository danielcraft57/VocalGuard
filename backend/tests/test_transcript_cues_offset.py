"""Tests offset cues SRT (accueil seed)."""

from backend.voice.transcript_cues import build_transcript_cues, offset_transcript_cues


def test_offset_transcript_cues_shifts_times():
    """Les timestamps avancent de la duree d'accueil."""
    cues = build_transcript_cues("Bonjour monsieur Daniel", duration_sec=4.0)
    assert cues
    shifted = offset_transcript_cues(cues, 4.2)
    assert shifted[0]["start"] == round(cues[0]["start"] + 4.2, 3)
    assert shifted[0]["end"] == round(cues[0]["end"] + 4.2, 3)
    assert shifted[0]["words"][0]["start"] == round(cues[0]["words"][0]["start"] + 4.2, 3)


def test_offset_zero_keeps_cues():
    """Offset nul = copie identique."""
    cues = build_transcript_cues("Oui", duration_sec=1.0)
    assert offset_transcript_cues(cues, 0.0)[0]["start"] == cues[0]["start"]
