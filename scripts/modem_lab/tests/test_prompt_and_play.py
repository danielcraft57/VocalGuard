"""Tests du scénario prompt_and_play (parsing et séquencement des clés)."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labscenarios.prompt_and_play import (  # noqa: E402
    _interactive_play,
    _parse_sequence,
    _parse_wav_binding,
    _play_keys,
    parse_args,
)


class PromptAndPlayTests(unittest.TestCase):
    def test_parse_wav_binding_ok(self) -> None:
        key, path = _parse_wav_binding("hello:assets/hello.wav")
        self.assertEqual(key, "hello")
        self.assertEqual(path, Path("assets/hello.wav"))

    def test_parse_wav_binding_invalid(self) -> None:
        with self.assertRaises(ValueError):
            _parse_wav_binding("hello_only")

    def test_parse_sequence(self) -> None:
        self.assertEqual(_parse_sequence("a,b, c ,,d"), ["a", "b", "c", "d"])

    def test_play_keys_stops_on_failure(self) -> None:
        bank = AsyncMock()
        bank.play = AsyncMock(side_effect=[True, False, True])

        async def run():
            return await _play_keys(
                bank,
                ["a", "b", "c"],
                prefer_already_in_voice=True,
                inter_key_delay_sec=0.0,
            )

        ok = asyncio.run(run())
        self.assertFalse(ok)
        self.assertEqual(bank.play.await_count, 2)

    def test_interactive_play_forwards_prefer_flag(self) -> None:
        bank = unittest.mock.MagicMock()
        bank.keys.return_value = ["welcome"]
        bank.play = AsyncMock(return_value=True)
        inputs = iter(["welcome", "q"])

        async def run():
            with unittest.mock.patch("builtins.input", side_effect=lambda *_: next(inputs)):
                await _interactive_play(bank, prefer_already_in_voice=False)

        asyncio.run(run())
        bank.play.assert_awaited_once_with("welcome", prefer_already_in_voice=False)

    def test_profile_mobile_calibrated_applies_bundle(self) -> None:
        argv = [
            "prompt_and_play.py",
            "--number",
            "1",
            "--wav",
            "w:w.wav",
            "--profile",
            "mobile-calibrated",
        ]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertEqual(args.wait_answer_or_voice_sec, 45.0)
        self.assertTrue(args.answer_on_voice_activity)
        self.assertTrue(args.answer_on_energy_fallback)
        self.assertEqual(args.min_voice_trigger_sec, 9.0)
        self.assertTrue(args.tone_reject)
        self.assertEqual(args.vad_threshold, 22.0)
        self.assertFalse(args.prepare_offhook)
        self.assertEqual(args.wait_hangup_sec, 15.0)

    def test_profile_explicit_cli_overrides_profile(self) -> None:
        argv = [
            "prompt_and_play.py",
            "--number",
            "1",
            "--wav",
            "w:w.wav",
            "--profile",
            "mobile-calibrated",
            "--wait-answer-or-voice-sec",
            "12",
            "--no-tone-reject",
        ]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertEqual(args.wait_answer_or_voice_sec, 12.0)
        self.assertFalse(args.tone_reject)


if __name__ == "__main__":
    unittest.main()

