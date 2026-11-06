"""
Session appel sortant / entrant (modem + audio).
"""

from __future__ import annotations

import asyncio
import queue
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backend.core.config import Config  # noqa: E402
from backend.core.modem_handler import ModemHandler  # noqa: E402
from desktop.modem_local_call import LiveAudioBridge, run_modem_call  # noqa: E402


async def run_outbound_call(
    *,
    number: str,
    com_port: Optional[str],
    baudrate: int,
    input_device: Optional[int],
    output_device: Optional[int],
    hangup_event: threading.Event,
    dtmf_queue: "queue.Queue[str]",
    ptt_queue: "queue.Queue[bool]",
    on_status: Callable[[str], None],
    on_line_level: Optional[Callable[[float], None]] = None,
    on_mic_level: Optional[Callable[[float], None]] = None,
    on_uplink_pcm: Optional[Callable[[bytes], None]] = None,
    on_downlink_pcm: Optional[Callable[[bytes], None]] = None,
    push_to_talk: bool = True,
    ptt_ms: int = 1200,
) -> None:
    """
    Appel sortant via run_modem_call.

    @param number Numero PSTN.
    @param com_port Port COM modem.
    """
    await run_modem_call(
        number=number,
        com_port=com_port,
        baudrate=baudrate,
        input_device=input_device,
        output_device=output_device,
        hangup_event=hangup_event,
        dtmf_queue=dtmf_queue,
        ptt_queue=ptt_queue,
        on_status=on_status,
        on_line_level=on_line_level,
        on_mic_level=on_mic_level,
        on_uplink_pcm=on_uplink_pcm,
        on_downlink_pcm=on_downlink_pcm,
        push_to_talk=push_to_talk,
        ptt_ms=ptt_ms,
    )


async def run_incoming_listen_loop(
    *,
    com_port: Optional[str],
    baudrate: int,
    stop_event: threading.Event,
    on_status: Callable[[str], None],
    on_ring: Callable[[], None],
    on_caller_id: Callable[[str, Optional[str]], None],
) -> None:
    """
    Ecoute RING / CID sans decrochage auto.

    @param stop_event Arret propre.
    @param on_ring Sonnerie sans numero.
    @param on_caller_id Numero + nom optionnel.
    """
    cfg_path = _REPO / "config" / "config.yaml"
    if not cfg_path.is_file():
        cfg_path = _REPO / "config" / "config.example.yaml"
    config = Config(config_path=cfg_path)
    if com_port:
        config.modem_port = com_port
    config.modem_baudrate = baudrate

    modem = ModemHandler(config.modem_port, config.modem_baudrate)
    modem.instant_ring_seize = False
    monitor_task: Optional[asyncio.Task] = None

    async def _incoming_cb(caller_id: Optional[str] = None, caller_name: Optional[str] = None, **_: object) -> None:
        if caller_id:
            on_caller_id(str(caller_id), caller_name)
        else:
            on_ring()

    try:
        on_status("Ecoute ligne entrante…")
        ok = await modem.initialize()
        if not ok:
            raise RuntimeError("Modem inaccessible.")
        modem.on_incoming_call = _incoming_cb
        monitor_task = asyncio.create_task(modem.monitor_calls(), name="prospector-incoming")
        while not stop_event.is_set():
            await asyncio.sleep(0.15)
    finally:
        if monitor_task is not None:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        try:
            await modem.hangup()
        except Exception:
            pass
        modem.close()
        on_status("Ecoute arretee.")


async def answer_incoming_call(
    *,
    com_port: Optional[str],
    baudrate: int,
    input_device: Optional[int],
    output_device: Optional[int],
    hangup_event: threading.Event,
    dtmf_queue: "queue.Queue[str]",
    ptt_queue: "queue.Queue[bool]",
    on_status: Callable[[str], None],
    on_line_level: Optional[Callable[[float], None]] = None,
    on_mic_level: Optional[Callable[[float], None]] = None,
    on_uplink_pcm: Optional[Callable[[bytes], None]] = None,
    on_downlink_pcm: Optional[Callable[[bytes], None]] = None,
    push_to_talk: bool = True,
    ptt_ms: int = 1200,
) -> None:
    """
    Decroche un entrant et demarre le pont audio.

    @param hangup_event Fin de session.
    """
    cfg_path = _REPO / "config" / "config.yaml"
    if not cfg_path.is_file():
        cfg_path = _REPO / "config" / "config.example.yaml"
    config = Config(config_path=cfg_path)
    if com_port:
        config.modem_port = com_port
    config.modem_baudrate = baudrate

    modem = ModemHandler(config.modem_port, config.modem_baudrate)
    bridge: Optional[LiveAudioBridge] = None
    try:
        on_status("Decrochage…")
        if not await modem.initialize():
            raise RuntimeError("Modem inaccessible.")
        ok, caller_id, _name = await modem.answer_call(fast_voice_seize=False)
        if not ok:
            raise RuntimeError("Echec decrochage.")
        on_status(f"En communication{f' — {caller_id}' if caller_id else ''}.")
        vrx_ok = await modem.start_outgoing_vrx_stream(already_in_voice_mode=True)
        if vrx_ok:
            bridge = LiveAudioBridge(
                modem,
                input_device_index=input_device,
                output_device_index=output_device,
                push_to_talk=push_to_talk,
                on_line_level=on_line_level,
                on_mic_level=on_mic_level,
                on_uplink_pcm=on_uplink_pcm,
                on_downlink_pcm=on_downlink_pcm,
            )
            if not await bridge.start():
                on_status("Audio casque indisponible.")
                bridge = None
        while not hangup_event.is_set():
            while not dtmf_queue.empty():
                try:
                    ch = str(dtmf_queue.get_nowait()).strip().upper()
                except queue.Empty:
                    break
                if ch:
                    from desktop.modem_local_call import send_dtmf_with_fallback

                    await send_dtmf_with_fallback(modem, ch)
            while not ptt_queue.empty():
                try:
                    ptt_queue.get_nowait()
                    if bridge is not None:
                        await bridge.push_to_talk_once(ptt_ms)
                except queue.Empty:
                    break
            await asyncio.sleep(0.04)
    finally:
        if bridge is not None:
            await bridge.stop()
        try:
            await modem.end_outgoing_vrx_stream()
        except Exception:
            pass
        try:
            await modem.hangup()
        except Exception:
            pass
        modem.close()
        on_status("Appel entrant termine.")
