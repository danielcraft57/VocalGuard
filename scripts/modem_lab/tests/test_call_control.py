"""Tests de la façade CallController (dial, hangup, DTMF, answer)."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.call_control import CallController, HangupStyle  # noqa: E402


class CallControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.modem = MagicMock()
        self.modem.dial_number = AsyncMock(return_value=(True, "OK"))
        self.modem.send_dtmf = AsyncMock(return_value=True)
        self.modem.hangup = AsyncMock(return_value=True)
        self.modem.answer_call = AsyncMock(return_value=(True, "0123", "Bob"))
        self.modem.enter_voice_codec_before_dial = AsyncMock(return_value=True)
        self.modem.enter_voice_line_for_outbound_dial = AsyncMock(return_value=True)
        self.modem.send_command_full = AsyncMock(return_value=b"OK\r\n")
        self.ctl = CallController(self.modem)

    def test_dial_delegates(self) -> None:
        async def run():
            ok, raw = await self.ctl.dial("0123456789", blind=False, timeout_sec=30.0)
            return ok, raw

        ok, raw = asyncio.run(run())
        self.assertTrue(ok)
        self.modem.dial_number.assert_awaited_once()
        call_kw = self.modem.dial_number.await_args
        self.assertEqual(call_kw.kwargs.get("blind"), False)
        self.assertEqual(call_kw.kwargs.get("timeout"), 30.0)

    def test_hangup_simple(self) -> None:
        async def run():
            return await self.ctl.hangup(HangupStyle.SIMPLE_ATH)

        self.assertTrue(asyncio.run(run()))
        self.modem.hangup.assert_awaited_once()

    def test_send_dtmf_sequence(self) -> None:
        async def run():
            return await self.ctl.send_dtmf("1 2#", inter_digit_delay_sec=0.0)

        self.assertTrue(asyncio.run(run()))
        self.assertEqual(self.modem.send_dtmf.await_count, 3)

    def test_answer_full(self) -> None:
        async def run():
            return await self.ctl.answer_full()

        ok, cid, name = asyncio.run(run())
        self.assertTrue(ok)
        self.assertEqual(cid, "0123")


if __name__ == "__main__":
    unittest.main()
