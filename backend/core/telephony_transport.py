"""
Abstraction transport telephonie (modem analogique vs VoIP).

Le modem USB reste le backend prod par defaut. VoIP (SIP/RTP) sera branche
derriere la meme interface ; pour l'instant VoipTransport est un stub loopback
(sans compte SIP) pour valider entrant + sortant full-duplex en PCM 16 kHz.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Deque, Optional, Protocol, runtime_checkable

from loguru import logger

from backend.core.modem_handler import ModemHandler
from backend.voice.modem_profile import USR_VOICE_PROFILE, ModemVoiceProfile


# PCM navigateur / session sortante : s16le mono 16 kHz.
VOIP_PCM_SAMPLE_RATE = 16000
VOIP_PCM_SAMPLE_WIDTH = 2
VOIP_PCM_BYTES_PER_SEC = VOIP_PCM_SAMPLE_RATE * VOIP_PCM_SAMPLE_WIDTH


class TelephonyBackend(str, Enum):
    """Backend telephonie selectionne via config."""

    MODEM = "modem"
    VOIP = "voip"
    DUAL = "dual"  # entrant modem + sortant voip (tests)


IncomingCallback = Callable[[str, Optional[str]], Awaitable[None]]


@runtime_checkable
class TelephonyTransport(Protocol):
    """
    Contrat minimal pour un transport telephonique.

    PCM sortant / loopback VoIP : s16le mono 16 kHz (meme contrat que le dialer).
    Le modem garde son profil natif en interne ; ModemTransport convertit si besoin
    via les helpers existants cote routes.
    """

    name: str
    is_initialized: bool
    on_incoming: Optional[IncomingCallback]

    async def start(self) -> bool:
        """Demarre le transport (port serie, stack SIP stub, ...)."""
        ...

    async def stop(self) -> None:
        """Arrete le transport proprement."""
        ...

    async def dial(self, phone_number: str, timeout: float = 25.0) -> tuple[bool, str]:
        """
        Compose un numero sortant.

        @param phone_number Numero a appeler.
        @param timeout Delai max (s).
        @returns (succes, detail texte).
        """
        ...

    async def answer(self) -> bool:
        """Decroche un appel entrant en attente."""
        ...

    async def hangup(self) -> bool:
        """Raccroche la session courante."""
        ...

    async def read_pcm(self, nbytes: int = 2048) -> bytes:
        """
        Lit du PCM ligne (ou echo loopback).

        @param nbytes Octets max.
        @returns PCM (peut etre vide).
        """
        ...

    async def write_pcm(self, pcm: bytes) -> bool:
        """
        Envoie du PCM micro / uplink vers la ligne.

        @param pcm Octets PCM.
        @returns True si ecriture OK.
        """
        ...

    async def send_dtmf(self, digit: str) -> bool:
        """
        Envoie un digit DTMF.

        @param digit Un caractere 0-9 * # A-D.
        @returns True si envoye.
        """
        ...

    def health_snapshot(self) -> dict[str, Any]:
        """Etat pour /health."""
        ...


@dataclass
class _VoipSession:
    """Session VoIP stub (sortante ou entrante)."""

    direction: str  # "out" | "in"
    phone_number: str
    connected: bool = False
    hangup: bool = False
    rx_queue: Deque[bytes] = field(default_factory=deque)
    tx_echo_pending: bytearray = field(default_factory=bytearray)
    opened_at: float = field(default_factory=time.monotonic)


class ModemTransport:
    """
    Adapte ModemHandler au contrat TelephonyTransport.

    Ne change pas le comportement prod : delegue presque tout au modem.
    """

    def __init__(self, modem: ModemHandler) -> None:
        """
        @param modem Instance ModemHandler deja creee (partagee avec CallManager).
        """
        self._modem = modem
        self.name = "modem"
        self.on_incoming: Optional[IncomingCallback] = None

    @property
    def modem(self) -> ModemHandler:
        """Acces direct au modem (compat CallManager / routes)."""
        return self._modem

    @property
    def is_initialized(self) -> bool:
        return bool(self._modem.is_initialized)

    async def start(self) -> bool:
        """
        Initialise le modem si besoin.

        @returns True si pret.
        """
        if self._modem.is_initialized:
            return True
        return bool(await self._modem.initialize())

    async def stop(self) -> None:
        """Ferme le port serie modem."""
        try:
            close_fn = getattr(self._modem, "close", None)
            if close_fn is None:
                return
            result = close_fn()
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.warning("ModemTransport.stop: {}", exc)

    async def dial(self, phone_number: str, timeout: float = 25.0) -> tuple[bool, str]:
        """Delegue ATD au modem."""
        return await self._modem.dial_number(phone_number, timeout=timeout)

    async def answer(self) -> bool:
        """Decroche via ATA / seize voix."""
        ok, _cid, _name = await self._modem.answer_call()
        return bool(ok)

    async def hangup(self) -> bool:
        """ATH modem."""
        return bool(await self._modem.hangup())

    async def read_pcm(self, nbytes: int = 2048) -> bytes:
        """Lit le flux VRX sortant (profil modem natif)."""
        return await self._modem.read_outgoing_vrx_chunk(nbytes)

    async def write_pcm(self, pcm: bytes) -> bool:
        """Ecrit en VTX (PCM deja au format modem)."""
        if not pcm:
            return True
        return bool(await self._modem.write_outgoing_vtx_u8(pcm))

    async def send_dtmf(self, digit: str) -> bool:
        """DTMF modem (AT+VTS ou in-band selon etat)."""
        return bool(await self._modem.send_dtmf(digit))

    def health_snapshot(self) -> dict[str, Any]:
        snap = self._modem.health_snapshot()
        snap["telephony_transport"] = self.name
        return snap


class VoipTransport:
    """
    Stub VoIP full-duplex sans compte SIP.

    - dial() ouvre une session echo : ce qu'on write_pcm revient en read_pcm.
    - simulate_incoming() declenche on_incoming puis attend answer().
    - PCM : s16le mono 16 kHz (contrat dialer navigateur).
    """

    def __init__(self) -> None:
        self.name = "voip"
        self.is_initialized = False
        self.on_incoming: Optional[IncomingCallback] = None
        self._session: Optional[_VoipSession] = None
        self._lock = asyncio.Lock()
        self._incoming_waiting: Optional[str] = None
        self._incoming_name: Optional[str] = None
        self._answer_event = asyncio.Event()
        self.voice_profile: ModemVoiceProfile = USR_VOICE_PROFILE

    async def start(self) -> bool:
        """
        Marque le stub pret (pas de registre SIP).

        @returns Toujours True.
        """
        self.is_initialized = True
        logger.info("VoipTransport stub pret (loopback, pas de compte SIP)")
        return True

    async def stop(self) -> None:
        """Ferme la session et desactive le stub."""
        async with self._lock:
            if self._session is not None:
                self._session.hangup = True
                self._session = None
        self.is_initialized = False

    async def dial(self, phone_number: str, timeout: float = 25.0) -> tuple[bool, str]:
        """
        Ouvre une session sortante loopback (echo PCM).

        @param phone_number Numero compose (journalise seulement).
        @param timeout Ignore (connexion immediate).
        @returns (True, detail).
        """
        _ = timeout
        number = (phone_number or "").strip() or "unknown"
        async with self._lock:
            self._session = _VoipSession(direction="out", phone_number=number, connected=True)
        logger.info("VoipTransport.dial loopback -> {}", number)
        return True, "voip_loopback_connected"

    async def answer(self) -> bool:
        """
        Decroche un appel entrant simule en attente.

        @returns True si une INVITE stub etait en attente.
        """
        async with self._lock:
            if not self._incoming_waiting:
                return False
            number = self._incoming_waiting
            self._session = _VoipSession(
                direction="in",
                phone_number=number,
                connected=True,
            )
            self._incoming_waiting = None
            self._incoming_name = None
        self._answer_event.set()
        logger.info("VoipTransport.answer (entrant simule)")
        return True

    async def hangup(self) -> bool:
        """Termine la session courante."""
        async with self._lock:
            if self._session is None:
                return True
            self._session.hangup = True
            self._session.connected = False
            self._session = None
        self._incoming_waiting = None
        return True

    async def read_pcm(self, nbytes: int = 2048) -> bytes:
        """
        Lit l'echo / le flux RX stub.

        @param nbytes Octets max.
        @returns PCM s16le (silence si file vide et session active).
        """
        async with self._lock:
            sess = self._session
            if sess is None or sess.hangup or not sess.connected:
                return b""
            if sess.rx_queue:
                chunk = sess.rx_queue.popleft()
                if len(chunk) > nbytes:
                    sess.rx_queue.appendleft(chunk[nbytes:])
                    return chunk[:nbytes]
                return chunk
            # Silence court pour garder le rythme full-duplex (anti underrun UI).
            n = max(0, int(nbytes))
            n -= n % VOIP_PCM_SAMPLE_WIDTH
            return bytes(n) if n else b""

    async def write_pcm(self, pcm: bytes) -> bool:
        """
        Ecrit l'uplink et le renvoie en echo sur la file RX (loopback).

        @param pcm PCM s16le 16 kHz.
        @returns False si pas de session.
        """
        if not pcm:
            return True
        async with self._lock:
            sess = self._session
            if sess is None or sess.hangup or not sess.connected:
                return False
            # Echo : le distant "repete" ce qu'on envoie (test duplex).
            sess.rx_queue.append(bytes(pcm))
            # Limite memoire (~2 s).
            max_bytes = VOIP_PCM_BYTES_PER_SEC * 2
            total = sum(len(x) for x in sess.rx_queue)
            while total > max_bytes and sess.rx_queue:
                dropped = sess.rx_queue.popleft()
                total -= len(dropped)
        return True

    async def send_dtmf(self, digit: str) -> bool:
        """
        Stub DTMF : journalise seulement.

        @param digit Digit a envoyer.
        @returns True si session active.
        """
        d = (digit or "").strip()[:1]
        async with self._lock:
            if self._session is None or not self._session.connected:
                return False
        logger.info("VoipTransport.send_dtmf stub digit={}", d)
        return True

    async def simulate_incoming(
        self,
        phone_number: str,
        caller_name: Optional[str] = None,
    ) -> bool:
        """
        Simule une INVITE entrante (tests / CI, sans DID).

        Declenche ``on_incoming`` puis attend un ``answer()`` cote app (timeout 30 s).

        @param phone_number Numero appelant.
        @param caller_name Nom CID optionnel.
        @returns True si callback invoque.
        """
        number = (phone_number or "").strip() or "anonymous"
        self._incoming_waiting = number
        self._incoming_name = caller_name
        self._answer_event.clear()
        cb = self.on_incoming
        if cb is None:
            logger.warning("VoipTransport.simulate_incoming: pas de callback on_incoming")
            return False
        await cb(number, caller_name)
        return True

    def health_snapshot(self) -> dict[str, Any]:
        """Etat stub pour /health."""
        sess = self._session
        return {
            "telephony_transport": self.name,
            "modem_initialized": False,
            "voip_stub": True,
            "voip_initialized": bool(self.is_initialized),
            "voip_session": None
            if sess is None
            else {
                "direction": sess.direction,
                "phone_number": sess.phone_number,
                "connected": sess.connected,
            },
            "voip_incoming_waiting": self._incoming_waiting,
        }


class DualTransport:
    """
    Backend dual : entrant via modem, sortant via VoIP stub.

    ``read_pcm`` / ``write_pcm`` / ``dial`` ciblent le VoIP ;
    ``answer`` / hangup entrant restent sur le modem si pas de session voip.
    """

    def __init__(self, modem: ModemTransport, voip: VoipTransport) -> None:
        """
        @param modem Transport modem (entrant).
        @param voip Transport VoIP stub (sortant).
        """
        self._modem = modem
        self._voip = voip
        self.name = "dual"
        self.on_incoming: Optional[IncomingCallback] = None

    @property
    def modem(self) -> ModemHandler:
        return self._modem.modem

    @property
    def voip(self) -> VoipTransport:
        return self._voip

    @property
    def is_initialized(self) -> bool:
        return bool(self._modem.is_initialized or self._voip.is_initialized)

    async def start(self) -> bool:
        m_ok = await self._modem.start()
        v_ok = await self._voip.start()
        # Entrant modem : brancher le callback modem -> on_incoming dual.
        if self.on_incoming is not None:
            self._voip.on_incoming = self.on_incoming

            async def _modem_incoming(cid: str, name: Optional[str] = None) -> None:
                cb = self.on_incoming
                if cb is not None:
                    await cb(cid, name)

            # ModemHandler utilise on_incoming_call(phone) parfois sans name —
            # on adapte via CallManager qui reste sur modem.on_incoming_call.
        return bool(m_ok or v_ok)

    async def stop(self) -> None:
        await self._voip.stop()
        await self._modem.stop()

    async def dial(self, phone_number: str, timeout: float = 25.0) -> tuple[bool, str]:
        return await self._voip.dial(phone_number, timeout=timeout)

    async def answer(self) -> bool:
        if self._voip._incoming_waiting:
            return await self._voip.answer()
        return await self._modem.answer()

    async def hangup(self) -> bool:
        v = await self._voip.hangup()
        m = await self._modem.hangup()
        return bool(v or m)

    async def read_pcm(self, nbytes: int = 2048) -> bytes:
        if self._voip._session is not None:
            return await self._voip.read_pcm(nbytes)
        return await self._modem.read_pcm(nbytes)

    async def write_pcm(self, pcm: bytes) -> bool:
        if self._voip._session is not None:
            return await self._voip.write_pcm(pcm)
        return await self._modem.write_pcm(pcm)

    async def send_dtmf(self, digit: str) -> bool:
        if self._voip._session is not None:
            return await self._voip.send_dtmf(digit)
        return await self._modem.send_dtmf(digit)

    def health_snapshot(self) -> dict[str, Any]:
        snap = self._modem.health_snapshot()
        snap.update(self._voip.health_snapshot())
        snap["telephony_transport"] = self.name
        return snap


def parse_telephony_backend(value: Optional[str]) -> TelephonyBackend:
    """
    Parse la valeur config / env.

    @param value modem | voip | dual.
    @returns Enum (defaut modem).
    """
    raw = (value or "modem").strip().lower()
    if raw in ("voip", "sip"):
        return TelephonyBackend.VOIP
    if raw == "dual":
        return TelephonyBackend.DUAL
    return TelephonyBackend.MODEM


def create_telephony_transport(
    backend: TelephonyBackend | str,
    *,
    modem: Optional[ModemHandler] = None,
) -> Any:
    """
    Factory transport selon le backend.

    @param backend modem | voip | dual.
    @param modem ModemHandler existant (requis pour modem/dual).
    @returns ModemTransport | VoipTransport | DualTransport.
    @raises ValueError Si modem manquant pour modem/dual.
    """
    kind = (
        backend
        if isinstance(backend, TelephonyBackend)
        else parse_telephony_backend(str(backend))
    )
    if kind == TelephonyBackend.VOIP:
        return VoipTransport()
    if modem is None:
        raise ValueError("ModemHandler requis pour backend modem/dual")
    modem_t = ModemTransport(modem)
    if kind == TelephonyBackend.DUAL:
        return DualTransport(modem_t, VoipTransport())
    return modem_t
