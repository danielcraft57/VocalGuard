"""Tests des helpers lecture/enregistrement ligne avec logique de fallback."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labcore.voice_line import play_wav_line_fallback, record_wav_line_fallback  # noqa: E402

_PCM_KW = {"pcm_u8": None, "pcm_rate": None}


class VoiceLineTests(unittest.TestCase):
    def test_fichier_absent_false(self) -> None:
        modem = AsyncMock()
        missing = Path("/nonexistent/modem_lab_message.wav")

        ok = asyncio.run(play_wav_line_fallback(modem, missing))

        self.assertFalse(ok)
        modem.play_wav_via_serial.assert_not_called()

    def test_succes_sur_premier_appel(self) -> None:
        modem = AsyncMock()
        modem.play_wav_via_serial = AsyncMock(side_effect=[True])
        wav = Path(__file__).resolve().parent / "__voice_line_dummy__.wav"
        wav.write_bytes(b"")

        try:
            ok = asyncio.run(play_wav_line_fallback(modem, wav))
        finally:
            wav.unlink(missing_ok=True)

        self.assertTrue(ok)
        self.assertEqual(modem.play_wav_via_serial.await_count, 1)
        modem.play_wav_via_serial.assert_any_call(
            wav, already_in_voice_mode=False, **_PCM_KW
        )

    def test_fallback_deuxieme_appel(self) -> None:
        modem = AsyncMock()
        modem.play_wav_via_serial = AsyncMock(side_effect=[False, True])
        wav = Path(__file__).resolve().parent / "__voice_line_dummy2__.wav"
        wav.write_bytes(b"")

        try:
            ok = asyncio.run(play_wav_line_fallback(modem, wav))
        finally:
            wav.unlink(missing_ok=True)

        self.assertTrue(ok)
        self.assertEqual(modem.play_wav_via_serial.await_count, 2)
        modem.play_wav_via_serial.assert_any_call(wav, already_in_voice_mode=False, **_PCM_KW)
        modem.play_wav_via_serial.assert_any_call(wav, already_in_voice_mode=True, **_PCM_KW)

    def test_les_deux_echec(self) -> None:
        modem = AsyncMock()
        modem.play_wav_via_serial = AsyncMock(side_effect=[False, False])
        wav = Path(__file__).resolve().parent / "__voice_line_dummy3__.wav"
        wav.write_bytes(b"")

        try:
            ok = asyncio.run(play_wav_line_fallback(modem, wav))
        finally:
            wav.unlink(missing_ok=True)

        self.assertFalse(ok)
        self.assertEqual(modem.play_wav_via_serial.await_count, 2)

    def test_prefer_already_in_voice_true_dabord(self) -> None:
        modem = AsyncMock()
        modem.play_wav_via_serial = AsyncMock(side_effect=[True])
        wav = Path(__file__).resolve().parent / "__voice_line_dummy4__.wav"
        wav.write_bytes(b"")

        try:
            ok = asyncio.run(play_wav_line_fallback(modem, wav, prefer_already_in_voice=True))
        finally:
            wav.unlink(missing_ok=True)

        self.assertTrue(ok)
        modem.play_wav_via_serial.assert_called_once_with(
            wav, already_in_voice_mode=True, **_PCM_KW
        )

    def test_prefer_already_in_voice_fallback_false(self) -> None:
        modem = AsyncMock()
        modem.play_wav_via_serial = AsyncMock(side_effect=[False, True])
        wav = Path(__file__).resolve().parent / "__voice_line_dummy5__.wav"
        wav.write_bytes(b"")

        try:
            ok = asyncio.run(play_wav_line_fallback(modem, wav, prefer_already_in_voice=True))
        finally:
            wav.unlink(missing_ok=True)

        self.assertTrue(ok)
        self.assertEqual(modem.play_wav_via_serial.await_count, 2)
        modem.play_wav_via_serial.assert_any_call(wav, already_in_voice_mode=True, **_PCM_KW)
        modem.play_wav_via_serial.assert_any_call(wav, already_in_voice_mode=False, **_PCM_KW)

    def test_record_prefer_voice_true_dabord(self) -> None:
        modem = AsyncMock()
        modem.record_wav_via_serial = AsyncMock(side_effect=[True])
        out = Path(__file__).resolve().parent / "__rec_dummy__.wav"

        try:
            ok = asyncio.run(record_wav_line_fallback(modem, 1.0, out, prefer_already_in_voice=True))
        finally:
            out.unlink(missing_ok=True)

        self.assertTrue(ok)
        modem.record_wav_via_serial.assert_called_once()
        c_args, c_kw = modem.record_wav_via_serial.call_args
        self.assertEqual(c_args[0], 1.0)
        self.assertTrue(c_kw.get("already_in_voice_mode"))


if __name__ == "__main__":
    unittest.main()
