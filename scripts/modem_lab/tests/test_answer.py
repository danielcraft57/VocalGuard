"""Tests du décroché entrant rapide (ATA rafale + fallback)."""

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.answer import fast_answer_incoming  # noqa: E402


class _SerialStub:
    is_open = True

    def __init__(self) -> None:
        self._dtr = True

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, val: bool) -> None:
        self._dtr = val


class MockModemFastAnswer:
    def __init__(self, ata_responses: list[bytes], answer_call_result: tuple[bool, str, str]) -> None:
        self.ata_responses = list(ata_responses)
        self.answer_call_result = answer_call_result
        self.ata_cmds: list[tuple[float, bytes]] = []

    async def send_command_full(self, cmd: str, timeout: float = 5.0, stop_on_ring: bool = True) -> bytes:
        if cmd == "ATA":
            resp = self.ata_responses.pop(0) if self.ata_responses else b""
            self.ata_cmds.append((timeout, resp))
            return resp
        return b"ERROR\r\n"

    async def answer_call(self) -> tuple[bool, str | None, str | None]:
        return self.answer_call_result

    serial_connection = _SerialStub()


class AnswerTests(unittest.TestCase):
    def test_fast_path_ok_sur_premiere_ata(self) -> None:
        m = MockModemFastAnswer([b"OK\r\n"], (False, None, None))

        ok, cid, name = asyncio.run(fast_answer_incoming(m, ata_attempts=3, ata_timeout=0.01, sleep_between=0))

        self.assertTrue(ok)
        self.assertEqual(cid, "-")
        self.assertEqual(name, "-")
        self.assertEqual(len(m.ata_cmds), 1)

    def test_fast_path_connect(self) -> None:
        m = MockModemFastAnswer([b"CONNECT\r\n"], (False, None, None))
        ok, _, _ = asyncio.run(fast_answer_incoming(m, ata_attempts=2, ata_timeout=0.01, sleep_between=0))
        self.assertTrue(ok)

    def test_fallback_answer_call_apres_echecs_ata(self) -> None:
        m = MockModemFastAnswer(
            [b"RING\r\n", b"RING\r\n", b"\r\n"],
            (True, "0781234567", "TEST"),
        )
        ok, cid, name = asyncio.run(fast_answer_incoming(m, ata_attempts=3, ata_timeout=0.01, sleep_between=0))
        self.assertTrue(ok)
        self.assertEqual(cid, "0781234567")
        self.assertEqual(name, "TEST")


if __name__ == "__main__":
    unittest.main()
