#!/usr/bin/env python3
"""
Diagnostic DTMF modem USB.

But:
- appeler un numero,
- tenter plusieurs methodes DTMF,
- afficher les reponses brutes modem pour identifier le blocage.
"""

import argparse
import asyncio
import math
import sys
import tempfile
import wave
from pathlib import Path

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import Config
from backend.core.modem_handler import ModemHandler


RATE = 8000
DTMF_FREQS = {
    "1": (697, 1209),
    "2": (697, 1336),
    "3": (697, 1477),
    "A": (697, 1633),
    "4": (770, 1209),
    "5": (770, 1336),
    "6": (770, 1477),
    "B": (770, 1633),
    "7": (852, 1209),
    "8": (852, 1336),
    "9": (852, 1477),
    "C": (852, 1633),
    "*": (941, 1209),
    "0": (941, 1336),
    "#": (941, 1477),
    "D": (941, 1633),
}


def generate_dtmf_u8(digit: str, duration_ms: int = 250, level: float = 0.8) -> bytes:
    clean = digit.strip().upper()
    pair = DTMF_FREQS.get(clean)
    if not pair:
        return b""
    f1, f2 = pair
    n = max(1, int(RATE * duration_ms / 1000))
    out = bytearray(n)
    for i in range(n):
        s = (
            math.sin(2.0 * math.pi * f1 * (i / RATE))
            + math.sin(2.0 * math.pi * f2 * (i / RATE))
        ) * 0.5
        out[i] = max(0, min(255, 128 + int(127 * level * s)))
    return bytes(out)


def write_u8_wav(path: Path, data: bytes) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(RATE)
        wf.writeframes(data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnostic DTMF modem")
    parser.add_argument("--number", required=True, help="Numero a appeler")
    parser.add_argument("--digit", default="3", help="Touche DTMF a tester (defaut: 3)")
    parser.add_argument("--port", default=None, help="Port modem (ex: COM6)")
    parser.add_argument("--baudrate", type=int, default=115200)
    return parser.parse_args()


async def run_diag(args: argparse.Namespace) -> int:
    config = Config(config_path=PROJECT_ROOT / "config" / "config.yaml")
    if args.port:
        config.modem_port = args.port
    config.modem_baudrate = args.baudrate

    modem = ModemHandler(config.modem_port, config.modem_baudrate)
    vrx_opened = False
    try:
        if not await modem.initialize():
            logger.error("Modem init echec")
            return 1

        ok, raw = await modem.dial_number(args.number)
        logger.info("Dial -> ok={} raw={}", ok, raw or "(vide)")
        if not ok:
            return 2

        await asyncio.sleep(1.0)
        vrx_opened = await modem.start_outgoing_vrx_stream(already_in_voice_mode=False)
        logger.info("VRX ouvert: {}", vrx_opened)
        await asyncio.sleep(0.5)

        d = args.digit.strip().upper()
        logger.info("=== Test DTMF '{}' ===", d)

        # Test 1: AT+VTS quote
        r1 = await modem.send_command_full(f'AT+VTS="{d}"', timeout=3.0, stop_on_ring=False)
        logger.info('AT+VTS="{}" -> {}', d, r1.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ") or "(vide)")
        await asyncio.sleep(0.5)

        # Test 2: AT+VTS brut
        r2 = await modem.send_command_full(f"AT+VTS={d}", timeout=3.0, stop_on_ring=False)
        logger.info("AT+VTS={} -> {}", d, r2.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ") or "(vide)")
        await asyncio.sleep(0.5)

        # Test 3: injection uplink half duplex
        tone = generate_dtmf_u8(d, duration_ms=280, level=0.75)
        r3 = await modem.half_duplex_send_uplink_u8(tone)
        logger.info("half_duplex_send_uplink_u8 -> {}", r3)
        await asyncio.sleep(0.7)

        # Test 4: WAV VTX
        silence = bytes([128]) * int(RATE * 0.08)
        burst = tone + silence + tone
        with tempfile.NamedTemporaryFile(prefix="dtmf_diag_", suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)
        try:
            write_u8_wav(wav_path, burst)
            r4 = await modem.play_wav_via_serial(wav_path, already_in_voice_mode=False)
            logger.info("play_wav_via_serial -> {}", r4)
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass

        logger.info("Diagnostic termine. Si aucun effet IVR, le blocage est cote modem/ligne.")
        return 0
    finally:
        if vrx_opened:
            try:
                await modem.end_outgoing_vrx_stream()
            except Exception:
                pass
        try:
            await modem.hangup()
        except Exception:
            pass
        modem.close()


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    raise SystemExit(asyncio.run(run_diag(parse_args())))

