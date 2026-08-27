"""Scenario lab CID : documentation executable (pas de modem requis pour l'import).

Sur node14, avec modem branche :

    python scripts/modem_lab_cid_wait.py --port /dev/ttyACM0 --wait 8

Attend RING + NMBR= puis logue la cause (ok / timeout / masque).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.phone_cid import classify_cid_outcome, normalize_cid_value  # noqa: E402


async def _run(port: str, wait_sec: float) -> int:
    import serial

    ser = serial.Serial(port, 115200, timeout=0.25)
    try:
        for cmd in (b"AT\r\n", b"ATE0\r\n", b"AT+FCLASS=0\r\n", b"AT+PCW=0\r\n", b"AT+VCID=1\r\n"):
            ser.write(cmd)
            time.sleep(0.2)
            _ = ser.read(256)
        print(f"Ecoute CID sur {port} pendant {wait_sec:.1f}s (appelez la ligne)...")
        deadline = time.monotonic() + wait_sec
        buf = b""
        got_ring = False
        cid = None
        while time.monotonic() < deadline:
            chunk = ser.read(256)
            if chunk:
                buf += chunk
                text = buf.decode("utf-8", errors="ignore")
                if "RING" in text.upper():
                    got_ring = True
                    print("RING")
                for line in text.replace("\r", "\n").split("\n"):
                    if "NMBR=" in line.upper():
                        raw = line.split("=", 1)[-1].strip()
                        cid = normalize_cid_value(raw)
                        print(f"NMBR brut={raw!r} normalise={cid!r}")
                        cause = classify_cid_outcome(
                            caller_id=cid,
                            source="ring",
                            timed_out=False,
                        )
                        print(f"cause={cause}")
                        return 0 if cid else 2
            await asyncio.sleep(0.05)
        print(
            "timeout",
            classify_cid_outcome(caller_id=None, source="ring", timed_out=True),
            "ring_seen=",
            got_ring,
        )
        return 1
    finally:
        ser.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Lab CID VocalGuard (USR5637)")
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--wait", type=float, default=20.0)
    args = p.parse_args()
    raise SystemExit(asyncio.run(_run(args.port, args.wait)))


if __name__ == "__main__":
    main()
