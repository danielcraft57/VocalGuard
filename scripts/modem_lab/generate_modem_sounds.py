#!/usr/bin/env python3
import asyncio

from labcore.bootstrap import setup_logging
from labaudio.sound_pack import run


if __name__ == "__main__":
    setup_logging("sound_pack")
    raise SystemExit(asyncio.run(run()))
