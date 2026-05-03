"""Tests de la banque de prompts WAV préchargés (WavBank)."""

import asyncio
import sys
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.line_audio_player import LineAudioPlayer  # noqa: E402
from labcore.wav_bank import WavBank  # noqa: E402


def _write_silence_wav(path: Path, frames: int = 400, rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(rate)
        wf.writeframes(b"\x80" * frames)


class WavBankTests(unittest.TestCase):
    def test_preload_and_play_by_key(self) -> None:
        modem = MagicMock()
        modem.play_wav_via_serial = AsyncMock(return_value=True)
        player = LineAudioPlayer(modem)
        bank = WavBank(player)
        with TemporaryDirectory() as td:
            p = Path(td) / "hello.wav"
            _write_silence_wav(p)
            bank.preload("hello", p)

            async def run():
                return await bank.play("hello", prefer_already_in_voice=True)

            self.assertTrue(asyncio.run(run()))
            modem.play_wav_via_serial.assert_awaited()

    def test_require_missing_key(self) -> None:
        modem = MagicMock()
        player = LineAudioPlayer(modem)
        bank = WavBank(player)
        with self.assertRaises(KeyError):
            bank.require("missing")


if __name__ == "__main__":
    unittest.main()

