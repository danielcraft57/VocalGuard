#!/usr/bin/env python3
"""
Enregistrement **ligne** (``AT+VRX`` → WAV) depuis un **thread** en planifiant la coroutine
sur la boucle asyncio qui possède le :class:`~backend.core.modem_handler.ModemHandler`.

Le port série du modem est protégé par un verrou asyncio : toute opération doit passer par
cette boucle. Ce module évite d'appeler ``asyncio.run()`` ou de bloquer un worker qui n'a
pas accès à la boucle principale (UI, queue synchrone, etc.).

Deux formes sont proposées:
- ``VrxWavRecorderThread`` : objet thread prêt à démarrer / rejoindre
- ``submit_vrx_wav_record`` : future concurrent sans créer de classe thread
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future as ConcurrentFuture
from pathlib import Path
from typing import Any, Optional

from loguru import logger


class VrxWavRecorderThread(threading.Thread):
    """
    Thread qui exécute ``record_wav_line_fallback`` ou ``modem.record_wav_via_serial`` via
    :func:`asyncio.run_coroutine_threadsafe` sur *loop*.

    * *loop* : la même boucle que celle utilisée pour ``await modem.initialize()`` etc.
    * *modem* : instance thread-safe uniquement si toutes les opérations série passent par *loop*.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        modem: Any,
        duration_sec: float,
        out_path: Path,
        *,
        prefer_already_in_voice: bool = True,
        stop_on_remote_hangup: bool = True,
        use_fallback: bool = True,
        daemon: bool = True,
        extra_timeout_sec: float = 30.0,
    ) -> None:
        """
        Paramètres:
        - loop: boucle asyncio qui possède le modem
        - duration_sec/out_path: durée d'enregistrement et destination WAV
        - prefer_already_in_voice: conserve le contexte voix déjà établi si possible
        - stop_on_remote_hangup: coupe l'enregistrement sur marqueurs de fin de ligne
        - use_fallback: passe par ``record_wav_line_fallback`` (recommandé)
        - extra_timeout_sec: marge au timeout (durée + marge)
        """
        super().__init__(daemon=daemon, name="vrx-wav-recorder")
        self._loop = loop
        self._modem = modem
        self._duration = float(duration_sec)
        self._out_path = Path(out_path)
        self._prefer_v = prefer_already_in_voice
        self._stop_hangup = stop_on_remote_hangup
        self._use_fallback = use_fallback
        self._extra = max(5.0, float(extra_timeout_sec))
        self._done = threading.Event()
        self._ok: Optional[bool] = None
        self._error: Optional[BaseException] = None

    def run(self) -> None:
        """Corps thread: planifie puis attend le résultat coroutine côté boucle modem."""
        try:
            if self._use_fallback:
                from labcore.voice_line import record_wav_line_fallback

                coro = record_wav_line_fallback(
                    self._modem,
                    self._duration,
                    self._out_path,
                    prefer_already_in_voice=self._prefer_v,
                    stop_on_remote_hangup=self._stop_hangup,
                )
            else:
                coro = self._modem.record_wav_via_serial(
                    self._duration,
                    self._out_path,
                    already_in_voice_mode=self._prefer_v,
                    stop_on_remote_hangup=self._stop_hangup,
                )
            fut: ConcurrentFuture[bool] = asyncio.run_coroutine_threadsafe(coro, self._loop)
            timeout = self._duration + self._extra
            self._ok = bool(fut.result(timeout=timeout))
        except BaseException as e:
            self._error = e
            logger.warning("Enregistrement VRX (thread) : {}", e)
        finally:
            self._done.set()

    def join_result(self, timeout: Optional[float] = None) -> bool:
        """``join`` puis retourne le succès ; False si exception ou timeout de *join*."""
        self.join(timeout=timeout)
        if not self._done.is_set():
            logger.warning("Enregistrement VRX (thread) : join timeout")
            return False
        if self._error is not None:
            return False
        return bool(self._ok)


def submit_vrx_wav_record(
    loop: asyncio.AbstractEventLoop,
    modem: Any,
    duration_sec: float,
    out_path: Path,
    *,
    prefer_already_in_voice: bool = True,
    stop_on_remote_hangup: bool = True,
    use_fallback: bool = True,
) -> ConcurrentFuture[bool]:
    """
    Planifie l'enregistrement sur *loop* sans créer de thread.

    Le caller récupère le résultat via ``.result(timeout=...)`` (thread synchrone) ou callback.
    """
    if use_fallback:
        from labcore.voice_line import record_wav_line_fallback

        coro = record_wav_line_fallback(
            modem,
            float(duration_sec),
            Path(out_path),
            prefer_already_in_voice=prefer_already_in_voice,
            stop_on_remote_hangup=stop_on_remote_hangup,
        )
    else:
        coro = modem.record_wav_via_serial(
            float(duration_sec),
            Path(out_path),
            already_in_voice_mode=prefer_already_in_voice,
            stop_on_remote_hangup=stop_on_remote_hangup,
        )
    return asyncio.run_coroutine_threadsafe(coro, loop)
