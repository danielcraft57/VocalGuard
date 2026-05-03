"""Tests des helpers techniques du scénario answering_machine."""

import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import labscenarios.answering_machine as voicemail  # noqa: E402


class AnsweringMachineHelperTests(unittest.TestCase):
    def test_generate_beep_longueur_minimale(self) -> None:
        raw = voicemail._generate_beep_u8(50, 1000)
        self.assertGreaterEqual(len(raw), 1)

    def test_enforce_wav_duree(self) -> None:
        raw = voicemail._generate_beep_u8(100, 800)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            p = Path(tmp.name)
        try:
            voicemail._write_u8_wav(p, raw, rate=8000)
            voicemail._enforce_wav_duration(p, 0.5)
            with wave.open(str(p), "rb") as wf:
                n = wf.getnframes()
                rate = wf.getframerate()
            self.assertEqual(n, int(rate * 0.5))
        finally:
            p.unlink(missing_ok=True)

    def test_enforce_truncates(self) -> None:
        pcm = bytes([128] * 8000)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            p = Path(tmp.name)
        try:
            voicemail._write_u8_wav(p, pcm, rate=8000)
            voicemail._enforce_wav_duration(p, 0.25)
            with wave.open(str(p), "rb") as wf:
                n = wf.getnframes()
            self.assertEqual(n, 2000)
        finally:
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
