"""Tests du lecteur audio ligne/local et du préchargement WAV."""

import asyncio
import sys
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.line_audio_player import (  # noqa: E402
    LineAudioPlayer,
    PreloadedWav,
    preview_wav_on_host,
)


def _write_silence_wav(path: Path, frames: int = 400, rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(rate)
        wf.writeframes(b"\x80" * frames)


class LineAudioPlayerTests(unittest.TestCase):
    def test_play_wav_delegates(self) -> None:
        modem = MagicMock()

        async def fake_play(*a, **k):
            return True

        modem.play_wav_via_serial = AsyncMock(return_value=True)
        with patch(
            "labcore.line_audio_player.play_wav_line_fallback",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_fb:
            player = LineAudioPlayer(modem)
            wav = Path("dummy.wav")

            async def run():
                return await player.play_wav(wav, prefer_already_in_voice=True)

            self.assertTrue(asyncio.run(run()))
            mock_fb.assert_awaited_once()

    def test_play_pcm_u8(self) -> None:
        modem = MagicMock()
        modem.play_wav_via_serial = AsyncMock(return_value=True)
        player = LineAudioPlayer(modem)

        async def run():
            return await player.play_pcm_u8(b"\x80\x90" * 100, prefer_already_in_voice=True)

        self.assertTrue(asyncio.run(run()))
        modem.play_wav_via_serial.assert_awaited()
        args, kwargs = modem.play_wav_via_serial.call_args
        self.assertEqual(kwargs.get("pcm_u8"), b"\x80\x90" * 100)

    def test_preload_then_play_preloaded(self) -> None:
        modem = MagicMock()
        modem.play_wav_via_serial = AsyncMock(return_value=True)
        player = LineAudioPlayer(modem)
        with TemporaryDirectory() as td:
            wav = Path(td) / "ready.wav"
            _write_silence_wav(wav, frames=500, rate=8000)
            item = player.preload_wav(wav)
            self.assertIsInstance(item, PreloadedWav)
            self.assertEqual(item.logical_name, "ready.wav")

            async def run():
                return await player.play_preloaded(item, prefer_already_in_voice=True)

            self.assertTrue(asyncio.run(run()))
            modem.play_wav_via_serial.assert_awaited()

    def test_preview_missing_file(self) -> None:
        async def run():
            return await preview_wav_on_host(Path("/nonexistent/nope.wav"))

        self.assertFalse(asyncio.run(run()))

    def test_preview_invokes_thread_when_audio_ok(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "t.wav"
            _write_silence_wav(p)
            with patch(
                "labcore.line_audio_player._play_s16_blocking",
                autospec=True,
            ) as mock_play:
                mock_play.return_value = None

                async def run():
                    return await preview_wav_on_host(p, max_rate_warn=False)

                self.assertTrue(asyncio.run(run()))
                mock_play.assert_called_once()


if __name__ == "__main__":
    unittest.main()
