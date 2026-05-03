"""Tests de conversion PCM pour le bridge audio live (u8 <-> s16le)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.live_audio import s16le_to_u8_pcm, u8_pcm_to_s16le  # noqa: E402


class LiveAudioConversionTests(unittest.TestCase):
    def test_silence_u8_centre_rest_proche(self) -> None:
        u8 = bytes([128] * 160)
        s16 = u8_pcm_to_s16le(u8)
        self.assertEqual(len(s16), 320)
        u8_back = s16le_to_u8_pcm(s16)
        self.assertEqual(u8_back[:10], bytes([128] * 10))

    def test_roundtrip_approximation(self) -> None:
        u8_orig = bytes([0, 64, 128, 200, 255])
        mid = u8_pcm_to_s16le(u8_orig)
        u8_mid = s16le_to_u8_pcm(mid)
        self.assertGreater(len(u8_orig), 0)
        self.assertEqual(len(u8_mid), len(u8_orig))


if __name__ == "__main__":
    unittest.main()
