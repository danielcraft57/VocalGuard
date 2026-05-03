"""Tests de la CLI unifiée modem_lab (routing sous-commandes)."""

import argparse
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli  # noqa: E402


class CliTests(unittest.TestCase):
    def test_build_command_with_separator(self) -> None:
        ns = argparse.Namespace(scenario="dialer", scenario_args=["--", "--port", "COM6", "--number", "147"])
        cmd = cli.build_command(ns)
        self.assertEqual(cmd[0], sys.executable)
        self.assertTrue(cmd[1].endswith(str(Path("labscenarios") / "dialer.py")))
        self.assertEqual(cmd[2:], ["--port", "COM6", "--number", "147"])

    def test_build_command_without_separator(self) -> None:
        ns = argparse.Namespace(scenario="smoke", scenario_args=["--port", "COM7"])
        cmd = cli.build_command(ns)
        self.assertEqual(cmd[2:], ["--port", "COM7"])

    def test_parser_accepts_known_scenario(self) -> None:
        ns = cli.build_parser().parse_args(["outbound-announce", "--", "--port", "COM6"])
        self.assertEqual(ns.scenario, "outbound-announce")


if __name__ == "__main__":
    unittest.main()

