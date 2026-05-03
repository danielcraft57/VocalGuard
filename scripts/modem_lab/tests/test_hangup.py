"""Tests du raccrochage turbo (séquence AT + impulsion DTR)."""

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.hangup import turbo_hangup  # noqa: E402


class _SerialHangupStub:
    is_open = True

    def __init__(self) -> None:
        self._dtr = True

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, val: bool) -> None:
        self._dtr = val


class MockModemHangup:
    def __init__(self, responses: list[bytes] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[str] = []

    async def send_command_full(self, cmd: str, timeout: float = 5.0, stop_on_ring: bool = True) -> bytes:
        self.calls.append(cmd)
        return self.responses.pop(0) if self.responses else b"ERROR\r\n"

    serial_connection = _SerialHangupStub()


class HangupTests(unittest.TestCase):
    def test_succes_via_no_carrier(self) -> None:
        m = MockModemHangup(
            [
                b"OK\r\n",
                b"OK\r\n",
                b"NO CARRIER\r\n",
                b"ERROR\r\n",
                b"ERROR\r\n",
                b"ERROR\r\n",
            ]
        )

        ok, cycles = asyncio.run(turbo_hangup(m, enable_console_beep=False, cmd_timeout=0.05))
        self.assertTrue(ok)
        self.assertEqual(cycles, 1)
        self.assertGreaterEqual(len(m.calls), 3)

    def test_succes_via_ok_ath(self) -> None:
        m = MockModemHangup(
            [
                b"OK\r\n",
                b"OK\r\n",
                b"RING\r\n",
                b"RING\r\n",
                b"OK\r\n",
                b"",
            ]
        )

        ok, cycles = asyncio.run(turbo_hangup(m, enable_console_beep=False, cmd_timeout=0.05))
        self.assertTrue(ok)
        self.assertEqual(cycles, 1)
        self.assertIn("ATH", m.calls)

    def test_echec_si_pas_ok_ni_carrier(self) -> None:
        m = MockModemHangup([b"\r\n", b"", b"", b"", b"", b"", b""])

        ok, cycles = asyncio.run(turbo_hangup(m, enable_console_beep=False, cmd_timeout=0.05))
        self.assertFalse(ok)
        self.assertEqual(cycles, 1)


if __name__ == "__main__":
    unittest.main()
