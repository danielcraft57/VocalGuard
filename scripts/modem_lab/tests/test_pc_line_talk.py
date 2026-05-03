"""Tests de session PC <-> ligne (orchestration VRX + bridge audio)."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.pc_line_talk import PcLineTalkSession  # noqa: E402


class PcLineTalkTests(unittest.TestCase):
    def test_start_stop_happy_path(self) -> None:
        modem = MagicMock()
        modem.start_outgoing_vrx_stream = AsyncMock(return_value=True)
        modem.end_outgoing_vrx_stream = AsyncMock(return_value=None)
        bridge = MagicMock()
        bridge.start = AsyncMock(return_value=True)
        bridge.stop = AsyncMock(return_value=None)
        bridge.push_to_talk_once = AsyncMock(return_value=None)
        sess = PcLineTalkSession(modem, bridge_factory=lambda *_a, **_k: bridge)

        async def run():
            ok = await sess.start(already_in_voice_mode=True)
            await sess.push_to_talk(400)
            await sess.stop()
            return ok

        self.assertTrue(asyncio.run(run()))
        modem.start_outgoing_vrx_stream.assert_awaited_once()
        bridge.start.assert_awaited_once()
        bridge.stop.assert_awaited_once()
        modem.end_outgoing_vrx_stream.assert_awaited_once()
        bridge.push_to_talk_once.assert_awaited_once_with(400)

    def test_start_fails_when_vrx_not_open(self) -> None:
        modem = MagicMock()
        modem.start_outgoing_vrx_stream = AsyncMock(return_value=False)
        modem.end_outgoing_vrx_stream = AsyncMock(return_value=None)
        bridge = MagicMock()
        bridge.start = AsyncMock(return_value=True)
        sess = PcLineTalkSession(modem, bridge_factory=lambda *_a, **_k: bridge)

        async def run():
            ok = await sess.start()
            await sess.stop()
            return ok

        self.assertFalse(asyncio.run(run()))
        bridge.start.assert_not_called()
        modem.end_outgoing_vrx_stream.assert_not_called()

    def test_start_fails_when_audio_unavailable(self) -> None:
        modem = MagicMock()
        modem.start_outgoing_vrx_stream = AsyncMock(return_value=True)
        modem.end_outgoing_vrx_stream = AsyncMock(return_value=None)
        bridge = MagicMock()
        bridge.start = AsyncMock(return_value=False)
        sess = PcLineTalkSession(modem, bridge_factory=lambda *_a, **_k: bridge)

        async def run():
            return await sess.start()

        self.assertFalse(asyncio.run(run()))
        modem.end_outgoing_vrx_stream.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

