"""Tests du détecteur d'activité vocale (speech start/end, adaptatif)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.pcm_tone import silence_u8, sine_u8  # noqa: E402
from labcore.voice_activity import (  # noqa: E402
    SpeechActivityDetector,
    VaKind,
)


class VoiceActivityTests(unittest.TestCase):
    def test_no_event_on_silence(self) -> None:
        det = SpeechActivityDetector(threshold=18.0, min_speech_ms=120.0)
        pcm = silence_u8(0.5)
        ev = det.feed(pcm)
        self.assertEqual(ev, [])

    def test_speech_start_on_tone(self) -> None:
        # Sinusoïde forte : MAD >> 18
        det = SpeechActivityDetector(
            threshold=10.0,
            min_speech_ms=100.0,
            hangover_ms=200.0,
            frame_ms=20.0,
        )
        pcm = sine_u8(duration_sec=0.4, amplitude=100.0)
        ev = []
        # flux par petits chunks comme le port série
        for i in range(0, len(pcm), 37):
            ev.extend(det.feed(pcm[i : i + 37]))
        kinds = [e.kind for e in ev]
        self.assertIn(VaKind.SPEECH_START, kinds)

    def test_speech_end_after_hangover(self) -> None:
        det = SpeechActivityDetector(
            threshold=10.0,
            min_speech_ms=40.0,
            hangover_ms=60.0,
            frame_ms=20.0,
        )
        pcm = sine_u8(duration_sec=0.15, amplitude=100.0) + silence_u8(0.3)
        ev = det.feed(pcm)
        kinds = [e.kind for e in ev]
        self.assertIn(VaKind.SPEECH_START, kinds)
        self.assertIn(VaKind.SPEECH_END, kinds)


if __name__ == "__main__":
    unittest.main()
