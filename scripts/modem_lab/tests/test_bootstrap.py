"""Tests bootstrap modem_lab (CLI args, build_modem, setup logging)."""

import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from loguru import logger as loguru_logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import labcore.bootstrap as bootstrap  # noqa: E402


class BootstrapParserTests(unittest.TestCase):
    def test_add_modem_args_sans_numero_obligatoire(self) -> None:
        p = argparse.ArgumentParser()
        bootstrap.add_modem_args(p, need_number=False)
        ns = p.parse_args(["--port", "COM99", "--baudrate", "57600"])
        self.assertEqual(ns.port, "COM99")
        self.assertEqual(ns.baudrate, 57600)

    def test_add_modem_args_numero_obligatoire(self) -> None:
        p = argparse.ArgumentParser()
        bootstrap.add_modem_args(p, need_number=True)
        with self.assertRaises(SystemExit):
            p.parse_args(["--port", "COM1"])

    def test_add_modem_args_avec_numero(self) -> None:
        p = argparse.ArgumentParser()
        bootstrap.add_modem_args(p, need_number=True)
        ns = p.parse_args(["--number", "0612345678", "--baudrate", "115200"])
        self.assertEqual(ns.number, "0612345678")


class BootstrapBuildModemTests(unittest.TestCase):
    def test_build_modem_override_port_et_baud(self) -> None:
        fake_cfg = MagicMock()
        fake_cfg.modem_port = "COM_OLD"
        fake_cfg.modem_baudrate = 115200

        ns = argparse.Namespace(port="COM7", baudrate=38400)

        with patch.object(bootstrap, "Config", return_value=fake_cfg):
            with patch.object(bootstrap, "ModemHandler") as mh:
                bootstrap.build_modem(ns)
        mh.assert_called_once_with("COM7", 38400)


class BootstrapLoggingTests(unittest.TestCase):
    def test_setup_logging_cree_fichier(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "scripts" / "modem_lab" / "logs").mkdir(parents=True)
            try:
                with patch.object(bootstrap, "PROJECT_ROOT", root):
                    lf = bootstrap.setup_logging(
                        "unittest_modem_lab",
                        console_level="ERROR",
                        clean_old_logs=False,
                    )
                self.assertTrue(lf.is_file())
            finally:
                # Sous Windows Loguru garde le fichier ouvert: liberer avant rmtree.
                loguru_logger.remove()


if __name__ == "__main__":
    unittest.main()
