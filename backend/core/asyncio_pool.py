"""
Executor par defaut de la boucle asyncio (borne pour limiter threads en prod).
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from loguru import logger

_installed = False


def default_pool_workers() -> int:
    """
    Nombre de workers du ThreadPoolExecutor asyncio.

    @returns Entier entre 1 et 16 (defaut 2 via VG_ASYNCIO_POOL_WORKERS).
    """
    raw = (os.getenv("VG_ASYNCIO_POOL_WORKERS") or "2").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 2
    return max(1, min(16, n))


def install_bounded_default_executor() -> None:
    """
    Remplace l executor par defaut (sinon min(32, cpu+4) threads Python).

    A appeler une fois au demarrage FastAPI (startup / lifespan).
    """
    global _installed
    if _installed:
        return
    workers = default_pool_workers()
    loop = asyncio.get_running_loop()
    loop.set_default_executor(
        ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vg_async")
    )
    _installed = True
    logger.info("Executor asyncio borne: max_workers={}", workers)
