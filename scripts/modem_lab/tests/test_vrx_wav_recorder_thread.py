"""Tests de l'enregistreur VRX planifié depuis un thread externe."""

import asyncio
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.vrx_wav_recorder_thread import (  # noqa: E402
    VrxWavRecorderThread,
    submit_vrx_wav_record,
)


def _start_loop_thread() -> tuple[asyncio.AbstractEventLoop, threading.Thread, threading.Event]:
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def runner() -> None:
        asyncio.set_event_loop(loop)
        ready.set()
        loop.run_forever()

    t = threading.Thread(target=runner, daemon=True, name="test-loop")
    t.start()
    ready.wait(timeout=5.0)
    return loop, t, ready


def _stop_loop_thread(loop: asyncio.AbstractEventLoop) -> None:
    loop.call_soon_threadsafe(loop.stop)


class VrxWavRecorderThreadTests(unittest.TestCase):
    def test_recorder_thread_runs_coro_on_foreign_loop(self) -> None:
        loop, bg, _ = _start_loop_thread()
        try:
            modem = MagicMock()
            modem.record_wav_via_serial = AsyncMock(return_value=True)
            out = Path("_test_vrx_thread.wav")
            rec = VrxWavRecorderThread(
                loop,
                modem,
                0.01,
                out,
                use_fallback=False,
                extra_timeout_sec=10.0,
            )
            rec.start()
            rec.join(15.0)
            self.assertTrue(rec.join_result(timeout=0.0))
            modem.record_wav_via_serial.assert_awaited()
        finally:
            _stop_loop_thread(loop)
            bg.join(timeout=2.0)

    def test_submit_returns_concurrent_future(self) -> None:
        loop, bg, _ = _start_loop_thread()
        try:
            modem = MagicMock()
            modem.record_wav_via_serial = AsyncMock(return_value=True)
            out = Path("_test_vrx_submit.wav")
            cf = submit_vrx_wav_record(
                loop,
                modem,
                0.01,
                out,
                use_fallback=False,
            )
            self.assertTrue(cf.result(timeout=10.0))
        finally:
            _stop_loop_thread(loop)
            bg.join(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
