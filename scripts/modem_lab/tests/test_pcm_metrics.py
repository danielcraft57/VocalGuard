"""Tests des métriques PCM utilitaires (MAD, RMS, framing)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.pcm_metrics import (  # noqa: E402
    frame_length_bytes,
    mean_abs_deviation_u8,
    rms_u8_centered,
    iter_complete_frames,
)


class PcmMetricsTests(unittest.TestCase):
    def test_silence_mad_zero(self) -> None:
        f = bytes([128] * 160)
        self.assertAlmostEqual(mean_abs_deviation_u8(f), 0.0)

    def test_frame_len_20ms_8k(self) -> None:
        self.assertEqual(frame_length_bytes(8000, 20.0), 160)

    def test_rms_full_scale(self) -> None:
        f = bytes([255, 0] * 80)
        r = rms_u8_centered(f)
        self.assertGreater(r, 80.0)

    def test_iter_frames(self) -> None:
        buf = bytearray()
        fl = 10
        out = list(iter_complete_frames(buf, b"\x00" * 25, fl))
        self.assertEqual(len(out), 2)
        self.assertEqual(len(buf), 5)


if __name__ == "__main__":
    unittest.main()
