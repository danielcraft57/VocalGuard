#!/usr/bin/env python3
import asyncio
from typing import Optional

from loguru import logger

RATE = 8000
CHANNELS = 1
FRAMES_PER_BUFFER = 160  # 20 ms at 8 kHz


def u8_pcm_to_s16le(raw_u8: bytes) -> bytes:
    out = bytearray(len(raw_u8) * 2)
    j = 0
    for b in raw_u8:
        s16 = (b - 128) << 8
        out[j] = s16 & 0xFF
        out[j + 1] = (s16 >> 8) & 0xFF
        j += 2
    return bytes(out)


def s16le_to_u8_pcm(raw_s16: bytes) -> bytes:
    out = bytearray(len(raw_s16) // 2)
    j = 0
    for i in range(0, len(raw_s16), 2):
        s16 = int.from_bytes(raw_s16[i : i + 2], "little", signed=True)
        out[j] = max(0, min(255, (s16 >> 8) + 128))
        j += 1
    return bytes(out)


class LiveAudioBridge:
    def __init__(
        self,
        modem,
        input_device_index: Optional[int] = None,
        output_device_index: Optional[int] = None,
        uplink_burst_ms: int = 260,
        rx_only: bool = False,
        push_to_talk: bool = False,
    ) -> None:
        self.modem = modem
        self.input_device_index = input_device_index
        self.output_device_index = output_device_index
        self.uplink_burst_ms = max(120, int(uplink_burst_ms))
        self.rx_only = rx_only
        self.push_to_talk = push_to_talk
        self.running = False
        self.tx_enabled = not push_to_talk
        self._ptt_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []
        self._pa = None
        self._sd = None
        self._backend = None
        self._in_stream = None
        self._out_stream = None

    async def start(self) -> bool:
        try:
            import pyaudio

            self._backend = "pyaudio"
            self._pa = pyaudio.PyAudio()
            self._in_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                input_device_index=self.input_device_index,
                frames_per_buffer=FRAMES_PER_BUFFER,
            )
            self._out_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=RATE,
                output=True,
                output_device_index=self.output_device_index,
                frames_per_buffer=FRAMES_PER_BUFFER,
            )
        except Exception:
            self._close_audio()
            try:
                import sounddevice as sd

                self._backend = "sounddevice"
                self._sd = sd
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
            except Exception as e:
                logger.error("Audio indisponible (pyaudio/sounddevice): {}", e)
                self._close_audio()
                return False

        self.running = True
        self._tasks = [asyncio.create_task(self._downlink_loop(), name="downlink_loop")]
        if not self.rx_only:
            self._tasks.append(asyncio.create_task(self._uplink_loop(), name="uplink_loop"))
        logger.info("Backend audio: {}", self._backend)
        logger.info("Mode audio: {}", "ecoute uniquement" if self.rx_only else "ecoute + micro")
        if self.push_to_talk and not self.rx_only:
            logger.info("Push-to-talk actif (commande 'v').")
        return True

    async def push_to_talk_once(self, duration_ms: int) -> None:
        if self.rx_only:
            return
        async with self._ptt_lock:
            self.tx_enabled = True
            try:
                await asyncio.sleep(max(0.1, duration_ms / 1000.0))
            finally:
                self.tx_enabled = False

    async def stop(self) -> None:
        self.running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug("Stop task audio: {}", e)
        self._tasks.clear()
        self._close_audio()

    async def _downlink_loop(self) -> None:
        while self.running:
            try:
                chunk = await self.modem.read_outgoing_vrx_chunk(1024)
                if not chunk:
                    await asyncio.sleep(0.01)
                    continue
                pcm16 = u8_pcm_to_s16le(chunk)
                await asyncio.to_thread(self._out_stream.write, pcm16)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug("Downlink audio: {}", e)
                await asyncio.sleep(0.05)

    async def _uplink_loop(self) -> None:
        burst_bytes_target = int((RATE * 2 * self.uplink_burst_ms) / 1000)
        burst_bytes_target = max(FRAMES_PER_BUFFER * 2, burst_bytes_target)
        pending = bytearray()
        while self.running:
            try:
                if not self.tx_enabled:
                    await asyncio.sleep(0.02)
                    continue
                if self._backend == "pyaudio":
                    data = await asyncio.to_thread(self._in_stream.read, FRAMES_PER_BUFFER, False)
                else:
                    data = await asyncio.to_thread(self._in_stream.read, FRAMES_PER_BUFFER)
                if isinstance(data, tuple):
                    data = data[0]
                pending.extend(data)
                if len(pending) < burst_bytes_target:
                    continue
                u8 = s16le_to_u8_pcm(bytes(pending))
                pending.clear()
                await self.modem.half_duplex_send_uplink_u8(u8)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug("Uplink audio: {}", e)
                await asyncio.sleep(0.05)

    def _close_audio(self) -> None:
        if self._in_stream is not None:
            try:
                if self._backend == "sounddevice":
                    self._in_stream.stop()
                    self._in_stream.close()
                else:
                    self._in_stream.stop_stream()
                    self._in_stream.close()
            except Exception:
                pass
            self._in_stream = None
        if self._out_stream is not None:
            try:
                if self._backend == "sounddevice":
                    self._out_stream.stop()
                    self._out_stream.close()
                else:
                    self._out_stream.stop_stream()
                    self._out_stream.close()
            except Exception:
                pass
            self._out_stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None
        self._sd = None
        self._backend = None
