#!/usr/bin/env python3
"""
Boucle asyncio : lit le flux PCM via ``ModemHandler.read_vrx_chunk`` (alias série VRX),
alimente un :class:`SpeechActivityDetector`, et invoque un callback pour chaque :class:`VaEvent`.

Prérequis : flux **AT+VRX** déjà ouvert (ex. ``await modem.start_outgoing_vrx_stream()``).

Les options ``log_latencies`` / ``print_events`` enregistrent l’heure (monotonic + horloge locale)
à chaque **speech_start** / **speech_end** pour estimer la latence entre la voix sur la ligne
et la détection VAD.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional, Tuple, Union

from loguru import logger

from labcore.voice_activity import SpeechActivityDetector, VaEvent, VaKind

Callback = Callable[[VaEvent], Union[None, Awaitable[None]]]


def _format_latency_line(
    ev: VaEvent,
    *,
    t_mono_start: float,
    label: str,
    wall: str,
) -> str:
    delay_ms = (time.monotonic() - t_mono_start) * 1000.0
    if ev.kind == VaKind.SPEECH_START:
        fr = "parole detectee (ca parle)"
    else:
        fr = "fin de parole (silence / hangover)"
    return (
        f"{label} {fr} | +{delay_ms:7.1f} ms depuis demarrage pompe | "
        f"metrique={ev.metric:.2f} | offset_pcm={ev.offset_end_bytes} | wall={wall}"
    )


async def _invoke(cb: Callback, ev: VaEvent) -> None:
    r = cb(ev)
    if inspect.isawaitable(r):
        await r


async def pump_vrx_speech_events(
    modem: Any,
    on_event: Callback,
    *,
    detector: Optional[SpeechActivityDetector] = None,
    chunk_size: int = 2048,
    stop_event: Optional[asyncio.Event] = None,
    max_seconds: Optional[float] = None,
    idle_sleep_sec: float = 0.02,
    max_events: Optional[int] = None,
    log_latencies: bool = True,
    print_events: bool = True,
    session_label: str = "VRX-VAD",
    stop_on_remote_hangup: bool = True,
) -> Tuple[int, Optional[str]]:
    """
    Lit ``modem.read_vrx_chunk(n)`` en boucle, passe les octets au détecteur, appelle ``on_event``.

    :param modem: instance ``ModemHandler`` (méthode async ``read_vrx_chunk``).
    :param log_latencies: journalise chaque événement (loguru) avec délai monotonic depuis le début de la pompe.
    :param print_events: affiche une ligne sur stdout (utile pour copier les timestamps en test manuel).
    :param session_label: préfixe des messages.
    :param stop_on_remote_hangup: si le modem expose ``vrx_remote_line_end_detected`` et que
        la fin de ligne apparaît dans le flux (NO CARRIER / ERROR…), arrête la pompe.
    :returns: ``(nombre d'événements dispatchés, raison d'arrêt ou None)`` —
        ``raison == 'remote_line_end'`` lorsque la détection hangup a coupé la boucle.
    """
    det = detector or SpeechActivityDetector()
    t0 = time.monotonic()
    dispatched = 0
    read_fn = getattr(modem, "read_vrx_chunk", None)
    if read_fn is None:
        read_fn = modem.read_outgoing_vrx_chunk

    if log_latencies or print_events:
        wall0 = datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3]
        banner = (
            f"{session_label} pompe demarree — delais '+xxx ms' depuis ce moment "
            f"(monotonic) | wall={wall0}"
        )
        if log_latencies:
            logger.info("{}", banner)
        if print_events:
            print(banner, flush=True)

    def _emit_latency_logs(ev: VaEvent) -> None:
        wall = datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3]
        line = _format_latency_line(ev, t_mono_start=t0, label=session_label, wall=wall)
        if log_latencies:
            logger.info("{}", line)
        if print_events:
            print(line, flush=True)

    hangup_fn = getattr(modem, "vrx_remote_line_end_detected", None)

    while True:
        if stop_event is not None and stop_event.is_set():
            return dispatched, None
        if max_seconds is not None and (time.monotonic() - t0) >= max_seconds:
            return dispatched, None
        if max_events is not None and dispatched >= max_events:
            return dispatched, None

        chunk = await read_fn(chunk_size)
        if stop_on_remote_hangup and hangup_fn is not None:
            try:
                hung_up = await hangup_fn()
            except Exception as e:
                logger.debug("vrx_remote_line_end_detected: {}", e)
                hung_up = False
            if hung_up:
                line = (
                    f"{session_label} arret : raccrochage distant / fin ligne (flux serie)."
                )
                if log_latencies:
                    logger.info("{}", line)
                if print_events:
                    print(line, flush=True)
                return dispatched, "remote_line_end"
        if not chunk:
            await asyncio.sleep(idle_sleep_sec)
            continue

        for ev in det.feed(chunk):
            _emit_latency_logs(ev)
            await _invoke(on_event, ev)
            dispatched += 1
            if max_events is not None and dispatched >= max_events:
                return dispatched, None
