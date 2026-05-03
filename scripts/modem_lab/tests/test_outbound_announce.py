"""Tests ciblés du scénario outbound_announce (calcul de délais sonnerie)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labscenarios.outbound_announce import compute_ringback_wait_sec  # noqa: E402


class OutboundAnnounceRingWaitTests(unittest.TestCase):
    def test_zero_si_pas_de_sonneries(self) -> None:
        self.assertEqual(compute_ringback_wait_sec(0, 5.0), 0.0)

    def test_produit_simple(self) -> None:
        self.assertEqual(compute_ringback_wait_sec(3, 5.0), 15.0)

    def test_negatif_traite_comme_zero(self) -> None:
        self.assertEqual(compute_ringback_wait_sec(-2, 5.0), 0.0)

    def test_duree_negative_traite_comme_zero(self) -> None:
        self.assertEqual(compute_ringback_wait_sec(4, -1.0), 0.0)


if __name__ == "__main__":
    unittest.main()
