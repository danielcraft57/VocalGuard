"""
Appel sortant modem USB local (PC Windows) : audio casque + AT.

Reutilise ModemHandler et la logique de scripts/modem_live_call_cli.py.
"""

from __future__ import annotations

import asyncio
import math
import queue
import sys
import tempfile
import threading
import wave
from pathlib import Path
from typing import Callable, Optional

import numpy as np

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backend.core.config import Config  # noqa: E402
from backend.core.modem_handler import ModemHandler, _unescape_dle_pcm  # noqa: E402
from backend.voice.audio_utils import pcm_modem_to_s16le_16k, pcm_s16le_16k_to_modem  # noqa: E402

RATE = 16000
CHANNELS = 1
FRAMES_PER_BUFFER = 320


def scale_pcm_s16le(pcm: bytes, gain: float) -> bytes:
    """
    Attenue ou amplifie un buffer PCM s16le mono.

    @param pcm Donnees brutes.
    @param gain Facteur 0.05..1.5.
    @returns PCM ajuste.
    """
    g = max(0.05, min(1.5, float(gain)))
    if g >= 0.999:
        return pcm
    if not pcm:
        return pcm
    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    scaled = np.clip(arr * g, -32768.0, 32767.0).astype(np.int16)
    return scaled.tobytes()

DTMF_FREQS = {
    "1": (697, 1209),
    "2": (697, 1336),
    "3": (697, 1477),
    "4": (770, 1209),
    "5": (770, 1336),
    "6": (770, 1477),
    "7": (852, 1209),
    "8": (852, 1336),
    "9": (852, 1477),
    "*": (941, 1209),
    "0": (941, 1336),
    "#": (941, 1477),
}


def list_com_ports() -> list[tuple[str, str]]:
    """
    Liste les ports serie (COM sous Windows).

    @returns Paires (device, description).
    """
    try:
        import serial.tools.list_ports

        return [(p.device, p.description or p.device) for p in serial.tools.list_ports.comports()]
    except Exception:
        return []


def u8_pcm_to_s16le(raw_u8: bytes, *, headroom: float = 0.92) -> bytes:
    """
    Convertit PCM 8-bit unsigned centré (128) en s16le avec marge anti-clipping.

    @param raw_u8 Trame modem VRX.
    @param headroom Facteur < 1 pour laisser de la tete avant saturation int16.
    @returns PCM s16le mono.
    """
    if not raw_u8:
        return b""
    hr = max(0.5, min(1.0, float(headroom)))
    u = np.frombuffer(raw_u8, dtype=np.uint8).astype(np.float32)
    x = (u - 128.0) / 128.0
    x = np.clip(x * hr, -1.0, 1.0)
    return (x * 32767.0).astype(np.int16).tobytes()


def generate_dtmf_u8(digit: str, duration_ms: int = 180, level: float = 0.55) -> bytes:
    """Genere une tonalite DTMF 8-bit mono 16 kHz."""
    clean = str(digit).strip().upper()
    pair = DTMF_FREQS.get(clean)
    if not pair:
        return b""
    f1, f2 = pair
    n_samples = max(1, int(RATE * duration_ms / 1000))
    fade_samples = min(40, n_samples // 8)
    out = bytearray(n_samples)
    for i in range(n_samples):
        amp = 1.0
        if i < fade_samples:
            amp = i / float(max(1, fade_samples))
        elif i >= n_samples - fade_samples:
            amp = (n_samples - i - 1) / float(max(1, fade_samples))
        s = (
            math.sin(2.0 * math.pi * f1 * (i / RATE))
            + math.sin(2.0 * math.pi * f2 * (i / RATE))
        ) * 0.5
        val = 128 + int(127 * level * amp * s)
        out[i] = max(0, min(255, val))
    return bytes(out)


def write_u8_wav(path: Path, u8_pcm: bytes) -> None:
    """Ecrit un WAV 8-bit mono."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(RATE)
        wf.writeframes(u8_pcm)


async def send_dtmf_with_fallback(modem: ModemHandler, digit: str) -> bool:
    """Envoie DTMF via AT+VTS ou fallback audio in-band."""
    if await modem.send_dtmf(digit):
        return True
    tone = generate_dtmf_u8(digit, duration_ms=320, level=0.82)
    if not tone:
        return False
    silence = bytes([128]) * int(RATE * 0.10)
    burst = tone + silence + tone + silence + tone
    ok1 = await modem.half_duplex_send_uplink_u8(burst)
    await asyncio.sleep(0.12)
    if ok1:
        return True
    try:
        with tempfile.NamedTemporaryFile(prefix="dtmf_", suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)
        write_u8_wav(wav_path, burst)
        try:
            ok = await modem.play_wav_via_serial(wav_path, already_in_voice_mode=True)
            await asyncio.sleep(0.20)
            return ok
        finally:
            wav_path.unlink(missing_ok=True)
    except OSError:
        ok1 = await modem.half_duplex_send_uplink_u8(tone)
        await asyncio.sleep(0.10)
        ok2 = await modem.half_duplex_send_uplink_u8(tone)
        await asyncio.sleep(0.12)
        return bool(ok1 or ok2)


class _VrxDownlinkAssembler:
    """
    Regroupe les octets VRX et convertit en s16le 16 kHz (moins de clics entre trames).
    """

    def __init__(self, modem: ModemHandler) -> None:
        self._modem = modem
        self._pending = bytearray()

    def feed(self, chunk: bytes) -> bytes:
        """
        Ajoute une trame modem et renvoie du PCM 16 kHz pret pour casque / WAV.

        @param chunk Octets bruts ``read_outgoing_vrx_chunk``.
        @returns PCM mono s16le 16 kHz (peut etre vide si tampon insuffisant).
        """
        if not chunk:
            return b""
        self._pending.extend(_unescape_dle_pcm(chunk))
        profile = self._modem.voice_profile
        width = max(1, int(profile.sample_width))
        min_bytes = max(width * 128, int(profile.bytes_per_sec) // 20)
        if len(self._pending) < min_bytes:
            return b""
        take = len(self._pending)
        if width == 2:
            take -= take % 2
        if take <= 0:
            return b""
        block = bytes(self._pending[:take])
        del self._pending[:take]
        return pcm_modem_to_s16le_16k(block, profile)

    def flush(self) -> bytes:
        """Vide le tampon restant en fin d'appel."""
        if not self._pending:
            return b""
        block = bytes(self._pending)
        self._pending.clear()
        return pcm_modem_to_s16le_16k(block, self._modem.voice_profile)


class LiveAudioBridge:
    """
    Pont modem VRX/VTX <-> micro / casque PC.

    @param on_line_level Callback RMS 0..1 (ligne entrant).
    @param on_mic_level Callback RMS 0..1 (micro montant).
    """

    def __init__(
        self,
        modem: ModemHandler,
        input_device_index: Optional[int] = None,
        output_device_index: Optional[int] = None,
        uplink_burst_ms: int = 260,
        push_to_talk: bool = True,
        on_line_level: Optional[Callable[[float], None]] = None,
        on_mic_level: Optional[Callable[[float], None]] = None,
        on_uplink_pcm: Optional[Callable[[bytes], None]] = None,
        on_downlink_pcm: Optional[Callable[[bytes], None]] = None,
        on_ptt_pcm: Optional[Callable[[bytes], None]] = None,
        line_gain: float = 0.22,
        mic_gain: float = 0.85,
    ) -> None:
        self.modem = modem
        self.input_device_index = input_device_index
        self.output_device_index = output_device_index
        self.line_gain = max(0.05, min(1.0, float(line_gain)))
        self.mic_gain = max(0.05, min(1.5, float(mic_gain)))
        self.uplink_burst_ms = max(120, int(uplink_burst_ms))
        self.push_to_talk = push_to_talk
        self.on_line_level = on_line_level
        self.on_mic_level = on_mic_level
        self.on_uplink_pcm = on_uplink_pcm
        self.on_downlink_pcm = on_downlink_pcm
        self.on_ptt_pcm = on_ptt_pcm
        self.running = False
        self.tx_enabled = not push_to_talk
        self._ptt_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []
        self._in_stream = None
        self._out_stream = None
        self._downlink = _VrxDownlinkAssembler(modem)

    async def start(self) -> bool:
        """Demarre les boucles audio."""
        try:
            import sounddevice as sd

            self._in_stream = sd.RawInputStream(
                samplerate=RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=FRAMES_PER_BUFFER,
                device=self.input_device_index,
            )
            self._out_stream = sd.RawOutputStream(
                samplerate=RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=FRAMES_PER_BUFFER,
                device=self.output_device_index,
            )
            self._in_stream.start()
            self._out_stream.start()
        except Exception:
            self._close_audio()
            return False

        self.running = True
        self._tasks = [asyncio.create_task(self._downlink_loop(), name="downlink")]
        if not self.push_to_talk:
            self._tasks.append(asyncio.create_task(self._uplink_loop(), name="uplink"))
        return True

    async def push_to_talk_once(self, duration_ms: int = 1200) -> None:
        """Ouvre le micro pour une rafale (mode PTT)."""
        if self._in_stream is None:
            return
        async with self._ptt_lock:
            try:
                burst_bytes_target = max(
                    FRAMES_PER_BUFFER * 2,
                    int((RATE * 2 * self.uplink_burst_ms) / 1000),
                )
                pending = bytearray()
                end = asyncio.get_event_loop().time() + max(0.15, duration_ms / 1000.0)
                while asyncio.get_event_loop().time() < end and self.running:
                    data = await asyncio.to_thread(self._in_stream.read, FRAMES_PER_BUFFER)
                    if isinstance(data, tuple):
                        data = data[0]
                    pending.extend(data)
                    if self.on_mic_level and data:
                        arr = np.frombuffer(data, dtype=np.int16)
                        rms = float(np.sqrt(np.mean(arr.astype(np.float64) ** 2))) / 32768.0
                        self.on_mic_level(min(1.0, rms * 4.0))
                    raw = bytes(data)
                    if self.on_ptt_pcm and raw:
                        self.on_ptt_pcm(raw)
                    if self.on_uplink_pcm and raw:
                        self.on_uplink_pcm(raw)
                    if len(pending) >= burst_bytes_target:
                        burst = scale_pcm_s16le(bytes(pending), self.mic_gain)
                        pending.clear()
                        uplink = pcm_s16le_16k_to_modem(burst, self.modem.voice_profile)
                        await self.modem.half_duplex_send_uplink_u8(uplink)
            except Exception:
                pass

    async def stop(self) -> None:
        """Arrete audio."""
        self.running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        tail = self._downlink.flush()
        if tail and self.on_downlink_pcm:
            self.on_downlink_pcm(tail)
        self._close_audio()

    def _close_audio(self) -> None:
        for stream in (self._in_stream, self._out_stream):
            if stream is None:
                continue
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self._in_stream = None
        self._out_stream = None

    async def _downlink_loop(self) -> None:
        while self.running:
            try:
                chunk = await self.modem.read_outgoing_vrx_chunk(2048)
                if not chunk:
                    await asyncio.sleep(0.01)
                    continue
                pcm16 = self._downlink.feed(chunk)
                if not pcm16:
                    continue
                if self.on_line_level and pcm16:
                    arr = np.frombuffer(pcm16, dtype=np.int16)
                    rms = float(np.sqrt(np.mean(arr.astype(np.float64) ** 2))) / 32768.0
                    self.on_line_level(min(1.0, rms * 4.0))
                if self.on_downlink_pcm and pcm16:
                    self.on_downlink_pcm(pcm16)
                out_pcm = scale_pcm_s16le(pcm16, self.line_gain)
                await asyncio.to_thread(self._out_stream.write, out_pcm)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(0.05)

    async def _uplink_loop(self) -> None:
        burst_bytes_target = max(FRAMES_PER_BUFFER * 2, int((RATE * 2 * self.uplink_burst_ms) / 1000))
        pending = bytearray()
        while self.running:
            try:
                if not self.tx_enabled:
                    await asyncio.sleep(0.02)
                    continue
                data = await asyncio.to_thread(self._in_stream.read, FRAMES_PER_BUFFER)
                if isinstance(data, tuple):
                    data = data[0]
                pending.extend(data)
                if self.on_mic_level and data:
                    arr = np.frombuffer(data, dtype=np.int16)
                    rms = float(np.sqrt(np.mean(arr.astype(np.float64) ** 2))) / 32768.0
                    self.on_mic_level(min(1.0, rms * 4.0))
                if self.on_uplink_pcm and data:
                    self.on_uplink_pcm(bytes(data))
                if len(pending) < burst_bytes_target:
                    continue
                burst = scale_pcm_s16le(bytes(pending), self.mic_gain)
                pending.clear()
                uplink = pcm_s16le_16k_to_modem(burst, self.modem.voice_profile)
                await self.modem.half_duplex_send_uplink_u8(uplink)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(0.05)


async def run_modem_call(
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
    on_ptt_pcm: Optional[Callable[[bytes], None]] = None,
    push_to_talk: bool = True,
    ptt_ms: int = 1200,
    line_gain: float = 0.22,
    mic_gain: float = 0.85,
    on_voice_ready: Optional[Callable[[], None]] = None,
    record_start_delay_s: float = 0.0,
) -> None:
    """
    Session complete : init modem, dial, audio live, DTMF jusqu'a raccrochage.

    @param number Numero a composer.
    @param com_port Port COM (ex. COM4).
    @param hangup_event Mis par l'UI pour raccrocher.
    @param dtmf_queue Touches a envoyer.
    @param ptt_queue Declenchements push-to-talk.
    @param on_status Messages utilisateur.
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
    vrx_opened = False

    try:
        on_status("Initialisation modem…")
        ok = await modem.initialize()
        if not ok:
            raise RuntimeError(
                "Modem inaccessible. Verifiez le cable USB, le port COM et config.yaml."
            )

        on_status(f"Composition {number}…")
        dial_ok, raw = await modem.dial_number(number)
        if not dial_ok:
            raise RuntimeError(f"Echec composition : {raw or 'reponse vide'}")

        on_status("Appel en cours — ecoute ligne.")
        vrx_opened = await modem.start_outgoing_vrx_stream(already_in_voice_mode=False)
        if not vrx_opened:
            on_status("Audio ligne indisponible — DTMF seulement.")
        elif on_voice_ready is not None:
            delay = max(0.0, float(record_start_delay_s))
            if delay > 0:
                await asyncio.sleep(delay)
            on_voice_ready()

        if vrx_opened:
            ptt_cb = (on_ptt_pcm if on_ptt_pcm is not None else on_uplink_pcm) if push_to_talk else None
            bridge = LiveAudioBridge(
                modem,
                input_device_index=input_device,
                output_device_index=output_device,
                push_to_talk=push_to_talk,
                on_line_level=on_line_level,
                on_mic_level=on_mic_level,
                on_uplink_pcm=None if push_to_talk else on_uplink_pcm,
                on_downlink_pcm=on_downlink_pcm,
                on_ptt_pcm=ptt_cb,
                line_gain=line_gain,
                mic_gain=mic_gain,
            )
            if not await bridge.start():
                on_status("Casque/micro indisponible — DTMF seulement.")
                bridge = None
            elif push_to_talk:
                on_status("Appuyez sur Parler pour parler.")

        while not hangup_event.is_set():
            while not dtmf_queue.empty():
                try:
                    ch = str(dtmf_queue.get_nowait()).strip().upper()
                except queue.Empty:
                    break
                if ch:
                    await send_dtmf_with_fallback(modem, ch)
                    on_status(f"DTMF {ch}")
            while not ptt_queue.empty():
                try:
                    ptt_queue.get_nowait()
                    if bridge is not None:
                        await bridge.push_to_talk_once(ptt_ms)
                except queue.Empty:
                    break
            await asyncio.sleep(0.04)

    finally:
        on_status("Fin d'appel…")
        if bridge is not None:
            await bridge.stop()
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
        on_status("Pret.")
