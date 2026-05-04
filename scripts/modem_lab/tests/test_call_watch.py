"""Tests des helpers d'attente décroché/voix et raccrochage distant."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.call_watch import wait_answer_or_voice_activity, wait_remote_hangup  # noqa: E402


class CallWatchTests(unittest.TestCase):
    def test_wait_answer_or_voice_prefers_answer_hint(self) -> None:
        modem = MagicMock(spec=["wait_voice_outbound_answer"])
        modem.wait_voice_outbound_answer = AsyncMock(return_value=(True, 1.0, False))

        async def run():
            return await wait_answer_or_voice_activity(modem, timeout_sec=5.0)

        ready, reason = asyncio.run(run())
        self.assertTrue(ready)
        self.assertEqual(reason, "answer_tone")

    def test_wait_answer_or_voice_detects_voice(self) -> None:
        pcm = bytes([80, 180]) * 2000
        modem = MagicMock(spec=["start_outgoing_vrx_stream", "end_outgoing_vrx_stream", "read_outgoing_vrx_chunk", "serial_connection"])
        modem.start_outgoing_vrx_stream = AsyncMock(return_value=True)
        modem.end_outgoing_vrx_stream = AsyncMock(return_value=None)
        modem.read_outgoing_vrx_chunk = AsyncMock(side_effect=[pcm, b"", b""])
        modem.serial_connection = None

        async def run():
            return await wait_answer_or_voice_activity(modem, timeout_sec=1.0)

        ready, reason = asyncio.run(run())
        self.assertTrue(ready)
        self.assertEqual(reason, "voice_activity")

    def test_wait_answer_or_voice_detects_carrier_rise(self) -> None:
        modem = MagicMock(spec=["start_outgoing_vrx_stream", "end_outgoing_vrx_stream", "read_outgoing_vrx_chunk", "serial_connection"])
        modem.start_outgoing_vrx_stream = AsyncMock(return_value=True)
        modem.end_outgoing_vrx_stream = AsyncMock(return_value=None)
        modem.read_outgoing_vrx_chunk = AsyncMock(side_effect=[b"", b"", b""])

        class _Carrier:
            def __init__(self) -> None:
                self._vals = iter([False, True, True])

            @property
            def cd(self) -> bool:
                return next(self._vals)

        modem.serial_connection = _Carrier()

        async def run():
            return await wait_answer_or_voice_activity(modem, timeout_sec=1.0)

        ready, reason = asyncio.run(run())
        self.assertTrue(ready)
        self.assertEqual(reason, "answer_tone")

    def test_wait_remote_hangup_from_marker(self) -> None:
        modem = MagicMock(spec=["start_outgoing_vrx_stream", "end_outgoing_vrx_stream", "read_outgoing_vrx_chunk"])
        modem.start_outgoing_vrx_stream = AsyncMock(return_value=True)
        modem.end_outgoing_vrx_stream = AsyncMock(return_value=None)
        modem.read_outgoing_vrx_chunk = AsyncMock(side_effect=[b"abc\r\nNO CARRIER\r\n"])

        async def run():
            return await wait_remote_hangup(modem, timeout_sec=1.0)

        hup, reason = asyncio.run(run())
        self.assertTrue(hup)
        self.assertEqual(reason, "remote_hangup")

    def test_wait_remote_hangup_from_carrier_drop(self) -> None:
        modem = MagicMock(spec=["start_outgoing_vrx_stream", "end_outgoing_vrx_stream", "read_outgoing_vrx_chunk", "serial_connection"])
        modem.start_outgoing_vrx_stream = AsyncMock(return_value=True)
        modem.end_outgoing_vrx_stream = AsyncMock(return_value=None)
        modem.read_outgoing_vrx_chunk = AsyncMock(side_effect=[b"", b""])

        class _Carrier:
            def __init__(self) -> None:
                self._vals = iter([True, False, False])

            @property
            def cd(self) -> bool:
                return next(self._vals)

        modem.serial_connection = _Carrier()

        async def run():
            return await wait_remote_hangup(modem, timeout_sec=1.0)

        hup, reason = asyncio.run(run())
        self.assertTrue(hup)
        self.assertEqual(reason, "remote_hangup")


if __name__ == "__main__":
    unittest.main()

