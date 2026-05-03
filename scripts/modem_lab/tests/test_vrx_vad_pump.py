"""Tests de la pompe VRX -> événements VAD."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.pcm_tone import sine_u8  # noqa: E402
from labcore.voice_activity import SpeechActivityDetector, VaKind  # noqa: E402
from labcore.vrx_vad_pump import pump_vrx_speech_events  # noqa: E402


class VrxPumpTests(unittest.TestCase):
    def test_pump_dispatches_speech_start(self) -> None:
        pcm = sine_u8(duration_sec=0.35, amplitude=100.0)
        modem = AsyncMock(spec=["read_vrx_chunk"])
        modem.read_vrx_chunk = AsyncMock(side_effect=[pcm[i : i + 80] for i in range(0, len(pcm), 80)] + [b""] * 200)

        events: list = []

        async def on_ev(ev):
            events.append(ev)

        det = SpeechActivityDetector(threshold=10.0, min_speech_ms=60.0, hangover_ms=100.0)

        async def run():
            return await pump_vrx_speech_events(
                modem,
                on_ev,
                detector=det,
                chunk_size=80,
                max_events=1,
                idle_sleep_sec=0.001,
                log_latencies=False,
                print_events=False,
            )

        n, reason = asyncio.run(run())
        self.assertEqual(n, 1)
        self.assertIsNone(reason)
        self.assertEqual(events[0].kind, VaKind.SPEECH_START)

    def test_async_callback(self) -> None:
        pcm = sine_u8(duration_sec=0.25, amplitude=100.0)
        modem = AsyncMock(spec=["read_vrx_chunk"])
        modem.read_vrx_chunk = AsyncMock(side_effect=[pcm] + [b""] * 50)

        seen = asyncio.Event()

        async def on_ev(ev):
            seen.set()

        async def run():
            return await pump_vrx_speech_events(
                modem,
                on_ev,
                detector=SpeechActivityDetector(threshold=10.0, min_speech_ms=40.0),
                max_events=1,
                idle_sleep_sec=0.001,
                log_latencies=False,
                print_events=False,
            )

        n, reason = asyncio.run(run())
        self.assertEqual(n, 1)
        self.assertIsNone(reason)
        self.assertTrue(seen.is_set())

    def test_fallback_read_outgoing(self) -> None:
        pcm = sine_u8(duration_sec=0.3, amplitude=100.0)

        class StubModem:
            def __init__(self) -> None:
                self.read_outgoing_vrx_chunk = AsyncMock(side_effect=[pcm] + [b""] * 30)

        modem = StubModem()
        count = []

        async def on_ev(ev):
            count.append(ev)

        async def run():
            return await pump_vrx_speech_events(
                modem,
                on_ev,
                detector=SpeechActivityDetector(threshold=10.0, min_speech_ms=40.0),
                max_events=1,
                idle_sleep_sec=0.001,
                log_latencies=False,
                print_events=False,
            )

        n, reason = asyncio.run(run())
        self.assertEqual(n, 1)
        self.assertIsNone(reason)
        self.assertEqual(len(count), 1)

    def test_stop_on_remote_hangup(self) -> None:
        pcm = b"\x80" * 64
        modem = AsyncMock(spec=["read_vrx_chunk", "vrx_remote_line_end_detected"])
        modem.read_vrx_chunk = AsyncMock(side_effect=[pcm] + [b""] * 200)
        modem.vrx_remote_line_end_detected = AsyncMock(side_effect=[False, True])

        async def on_ev(_):
            pass

        async def run():
            return await pump_vrx_speech_events(
                modem,
                on_ev,
                detector=SpeechActivityDetector(threshold=100.0, min_speech_ms=200.0),
                chunk_size=32,
                idle_sleep_sec=0.001,
                log_latencies=False,
                print_events=False,
                stop_on_remote_hangup=True,
            )

        n, reason = asyncio.run(run())
        self.assertEqual(reason, "remote_line_end")
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
