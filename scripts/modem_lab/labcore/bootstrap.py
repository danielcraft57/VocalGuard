#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import Config
from backend.core.modem_handler import ModemHandler


def add_modem_args(parser: argparse.ArgumentParser, need_number: bool = False) -> None:
    parser.add_argument("--port", default=None, help="Port modem (ex: COM6)")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baudrate modem")
    if need_number:
        parser.add_argument("--number", required=True, help="Numero a appeler")


def build_modem(args: argparse.Namespace) -> ModemHandler:
    config = Config(config_path=PROJECT_ROOT / "config" / "config.yaml")
    if args.port:
        config.modem_port = args.port
    config.modem_baudrate = args.baudrate
    return ModemHandler(config.modem_port, config.modem_baudrate)


def setup_logging(
    app_name: str = "modem_lab",
    console_level: str = "INFO",
    clean_old_logs: bool = True,
) -> Path:
    log_dir = PROJECT_ROOT / "scripts" / "modem_lab" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    if clean_old_logs:
        # Nettoie les anciens logs pour garder uniquement la session courante.
        for old in log_dir.glob("*.log"):
            try:
                old.unlink()
            except Exception:
                pass
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{app_name}_{stamp}.log"

    logger.remove()
    logger.add(
        sys.stderr,
        level=console_level.upper(),
        colorize=True,
        backtrace=False,
        diagnose=False,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>",
    )
    logger.add(
        str(log_file),
        level="DEBUG",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        rotation="10 MB",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )
    logger.debug("Logging initialise pour {}", app_name)
    logger.info("Fichier de logs: {}", log_file)
    return log_file

