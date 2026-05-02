#!/usr/bin/env python3
"""
Appel sortant interactif via modem USB (AT commands + audio live).

Fonctions:
- composer un numero (ATD),
- entendre l'interlocuteur (flux VRX -> haut-parleurs PC),
- parler avec le micro (micro PC -> modem via VTX half-duplex),
- envoyer des touches DTMF pendant l'appel.

Exemple:
  python scripts/modem_live_call_cli.py --number 0612345678 --port COM4
"""

import argparse
import asyncio
import math
import sys
import tempfile
import wave
from pathlib import Path
from typing import Optional

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import Config
from backend.core.modem_handler import ModemHandler


RATE = 8000
CHANNELS = 1
FRAMES_PER_BUFFER = 160  # 20 ms a 8 kHz
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


def u8_pcm_to_s16le(raw_u8: bytes) -> bytes:
    """Convertit des echantillons 8-bit unsigned en PCM 16-bit little-endian."""
    out = bytearray(len(raw_u8) * 2)
    j = 0
    for b in raw_u8:
        s16 = (b - 128) << 8
        out[j] = s16 & 0xFF
        out[j + 1] = (s16 >> 8) & 0xFF
        j += 2
    return bytes(out)


def s16le_to_u8_pcm(raw_s16: bytes) -> bytes:
    """Convertit du PCM 16-bit little-endian en 8-bit unsigned."""
    out = bytearray(len(raw_s16) // 2)
    j = 0
    for i in range(0, len(raw_s16), 2):
        s16 = int.from_bytes(raw_s16[i : i + 2], "little", signed=True)
        out[j] = max(0, min(255, (s16 >> 8) + 128))
        j += 1
    return bytes(out)


def generate_dtmf_u8(digit: str, duration_ms: int = 180, level: float = 0.55) -> bytes:
    """Genere une tonalite DTMF 8-bit unsigned 8 kHz pour injection in-band."""
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
    """Ecrit un WAV 8-bit mono 8 kHz."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(RATE)
        wf.writeframes(u8_pcm)


async def send_dtmf_with_fallback(modem: ModemHandler, digit: str) -> bool:
    """Envoie une touche DTMF via AT+VTS, puis fallback in-band audio si besoin."""
    if await modem.send_dtmf(digit):
        return True
    tone = generate_dtmf_u8(digit, duration_ms=320, level=0.82)
    if not tone:
        return False
    silence = bytes([128]) * int(RATE * 0.10)
    burst = tone + silence + tone + silence + tone
    # Priorite a l'injection half-duplex: c'est le mode qui fonctionne sur ce modem.
    ok1 = await modem.half_duplex_send_uplink_u8(burst)
    await asyncio.sleep(0.12)
    if ok1:
        return True
    try:
        with tempfile.NamedTemporaryFile(prefix="dtmf_", suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)
        write_u8_wav(wav_path, burst)
        try:
            # Fallback secondaire: VTX direct en restant dans le contexte voix courant.
            ok = await modem.play_wav_via_serial(wav_path, already_in_voice_mode=True)
            await asyncio.sleep(0.20)
            return ok
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        # Dernier fallback: une impulsion simple.
        ok1 = await modem.half_duplex_send_uplink_u8(tone)
        await asyncio.sleep(0.10)
        ok2 = await modem.half_duplex_send_uplink_u8(tone)
        await asyncio.sleep(0.12)
        return bool(ok1 or ok2)


class LiveAudioBridge:
    """Pont audio entre le flux modem VRX/VTX et les peripheriques du PC."""

    def __init__(
        self,
        modem: ModemHandler,
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
        """Initialise les streams audio et demarre les boucles TX/RX."""
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
                logger.error(
                    "Audio indisponible. Installe pyaudio ou sounddevice. Erreur: {}",
                    e,
                )
                self._close_audio()
                return False

        self.running = True
        self._tasks = [asyncio.create_task(self._downlink_loop(), name="downlink_loop")]
        if not self.rx_only:
            self._tasks.append(asyncio.create_task(self._uplink_loop(), name="uplink_loop"))
        logger.info("Backend audio utilise: {}", self._backend)
        logger.info(
            "Mode audio: {} (uplink_burst_ms={})",
            "ecoute uniquement" if self.rx_only else "ecoute + micro",
            self.uplink_burst_ms,
        )
        if self.push_to_talk and not self.rx_only:
            logger.info("Push-to-talk actif: le micro est coupe tant que tu n'appuies pas sur 'v'.")
        return True

    async def push_to_talk_once(self, duration_ms: int) -> None:
        """Active temporairement le micro pour une courte prise de parole."""
        if self.rx_only:
            return
        async with self._ptt_lock:
            self.tx_enabled = True
            try:
                await asyncio.sleep(max(0.1, duration_ms / 1000.0))
            finally:
                self.tx_enabled = False

    async def stop(self) -> None:
        """Arrete les boucles audio et ferme les streams."""
        self.running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug("Task audio stop: {}", e)
        self._tasks.clear()
        self._close_audio()

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

    async def _downlink_loop(self) -> None:
        """Lit l'audio du modem et le joue sur les haut-parleurs."""
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
        """Capture le micro et l'envoie vers le modem."""
        burst_bytes_target = int((RATE * 2 * self.uplink_burst_ms) / 1000)
        burst_bytes_target = max(FRAMES_PER_BUFFER * 2, burst_bytes_target)
        pending = bytearray()
        while self.running:
            try:
                if not self.tx_enabled:
                    await asyncio.sleep(0.02)
                    continue
                if self._backend == "pyaudio":
                    data = await asyncio.to_thread(
                        self._in_stream.read,
                        FRAMES_PER_BUFFER,
                        False,
                    )
                else:
                    data = await asyncio.to_thread(self._in_stream.read, FRAMES_PER_BUFFER)
                if isinstance(data, tuple):
                    # sounddevice retourne (bytes, overflowed)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Appel modem USB interactif")
    parser.add_argument("--number", required=True, help="Numero a appeler (ex: 0612345678)")
    parser.add_argument("--port", default=None, help="Port modem (ex: COM4). Auto-detect si vide.")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baudrate modem (defaut: 115200)")
    parser.add_argument("--input-device", type=int, default=None, help="Index device micro PyAudio")
    parser.add_argument("--output-device", type=int, default=None, help="Index device haut-parleur PyAudio")
    parser.add_argument(
        "--uplink-burst-ms",
        type=int,
        default=260,
        help="Taille des rafales micro envoyees au modem (ms, defaut: 260). Plus haut = plus fluide en ecoute.",
    )
    parser.add_argument(
        "--rx-only",
        action="store_true",
        help="Ecoute uniquement (coupe l'envoi micro) pour maximiser la fluidite.",
    )
    parser.add_argument(
        "--push-to-talk",
        action="store_true",
        help="Micro coupe par defaut. Appuie sur 'v' dans la console pour parler par rafales.",
    )
    parser.add_argument(
        "--ptt-ms",
        type=int,
        default=1200,
        help="Duree d'une prise de parole avec la touche 'v' (ms, defaut: 1200).",
    )
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="Desactive le pont audio live (garde dial + DTMF)",
    )
    parser.add_argument(
        "--list-audio-devices",
        action="store_true",
        help="Affiche les devices PyAudio puis quitte",
    )
    return parser.parse_args()


def list_audio_devices() -> None:
    """Liste les peripheriques audio disponibles via PyAudio ou sounddevice."""
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        try:
            count = pa.get_device_count()
            print("Peripheriques audio detectes (pyaudio):")
            for i in range(count):
                info = pa.get_device_info_by_index(i)
                max_in = int(info.get("maxInputChannels", 0))
                max_out = int(info.get("maxOutputChannels", 0))
                print(f"[{i}] {info.get('name')} (in={max_in}, out={max_out})")
            return
        finally:
            pa.terminate()
    except ImportError:
        pass
    except Exception:
        pass

    try:
        import sounddevice as sd

        print("Peripheriques audio detectes (sounddevice):")
        for i, info in enumerate(sd.query_devices()):
            max_in = int(info.get("max_input_channels", 0))
            max_out = int(info.get("max_output_channels", 0))
            print(f"[{i}] {info.get('name')} (in={max_in}, out={max_out})")
    except Exception as e:
        print(f"Impossible de lister les devices audio: {e}")
        print("Installe pyaudio ou sounddevice.")


async def interactive_loop(
    modem: ModemHandler,
    bridge: Optional[LiveAudioBridge] = None,
    push_to_talk: bool = False,
    ptt_ms: int = 1200,
) -> None:
    """Boucle console pour DTMF et raccrochage."""
    print("Commandes:")
    print("- Tape une touche DTMF: 0-9, *, #, A-D")
    print("- Tu peux aussi taper plusieurs touches d'un coup, ex: 123#")
    if push_to_talk and bridge is not None:
        print(f"- v: parler {ptt_ms} ms (push-to-talk)")
    print("- h: raccrocher")
    print("- q: quitter")
    try:
        while True:
            cmd = (await asyncio.to_thread(input, "DTMF/h/q > ")).strip().upper()
            if not cmd:
                continue
            if cmd in {"Q", "QUIT"}:
                break
            if cmd in {"H", "HANGUP"}:
                await modem.hangup()
                break
            if cmd in {"V", "VOICE"} and push_to_talk and bridge is not None:
                print(f"Micro ouvert {ptt_ms} ms...")
                await bridge.push_to_talk_once(ptt_ms)
                continue

            sent_any = False
            for ch in cmd:
                ok = await send_dtmf_with_fallback(modem, ch)
                if ok:
                    sent_any = True
                    print(f"DTMF envoye: {ch}")
                else:
                    print(f"Echec envoi DTMF modem: {ch}")
            if not sent_any:
                print("Aucune touche valide envoyee.")
    except asyncio.CancelledError:
        return
    except KeyboardInterrupt:
        return


async def run_call(args: argparse.Namespace) -> int:
    """Initialise le modem, lance l'appel et gere la session interactive."""
    config = Config(config_path=PROJECT_ROOT / "config" / "config.yaml")
    if args.port:
        config.modem_port = args.port
    config.modem_baudrate = args.baudrate

    modem = ModemHandler(config.modem_port, config.modem_baudrate)
    bridge: Optional[LiveAudioBridge] = None
    vrx_opened = False

    try:
        ok = await modem.initialize()
        if not ok:
            logger.error("Modem non initialise. Verifie le port (ex: COM4) et les droits.")
            return 1

        dial_ok, raw = await modem.dial_number(args.number)
        logger.info("Reponse modem dial: {}", raw or "(vide)")
        if not dial_ok:
            logger.error("Echec composition. Verifie numero, ligne et couverture.")
            return 2

        logger.info("Appel etabli ou en cours. Session interactive demarree.")

        vrx_opened = await modem.start_outgoing_vrx_stream(already_in_voice_mode=False)
        if not vrx_opened:
            logger.warning("Flux audio VRX non ouvert. Audio live indisponible, DTMF ok.")

        if not args.no_audio and vrx_opened:
            bridge = LiveAudioBridge(
                modem=modem,
                input_device_index=args.input_device,
                output_device_index=args.output_device,
                uplink_burst_ms=args.uplink_burst_ms,
                rx_only=args.rx_only,
                push_to_talk=args.push_to_talk,
            )
            audio_ok = await bridge.start()
            if audio_ok:
                logger.info("Audio live actif (micro + ecoute).")
            else:
                logger.warning("Audio live indisponible. Continue avec DTMF/hangup.")

        await interactive_loop(
            modem,
            bridge=bridge,
            push_to_talk=args.push_to_talk,
            ptt_ms=args.ptt_ms,
        )
        return 0

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Arret demande par l'utilisateur.")
        return 0
    finally:
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


def setup_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO")


if __name__ == "__main__":
    setup_logging()
    cli_args = parse_args()

    if cli_args.list_audio_devices:
        list_audio_devices()
        raise SystemExit(0)

    raise SystemExit(asyncio.run(run_call(cli_args)))
