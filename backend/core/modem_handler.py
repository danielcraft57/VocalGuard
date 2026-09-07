"""
Gestionnaire de modem pour la communication téléphonique.

Supporte deux façons de jouer un WAV vers la ligne :
- ALSA (aplay) : le modem expose une carte son, on joue sur ce device.
- Mode voix série (comme callattendant) : commandes AT+FCLASS=8, AT+VTX puis envoi
  des trames PCM (USR : 16-bit 11 kHz ; Conexant : 8-bit 8 kHz) sur le port série.
  Voir https://github.com/emxsys/callattendant (modem USR 5637 / Conexant).
"""

import asyncio
import concurrent.futures
import errno
import math
import threading
import time
import wave
import re
from functools import partial
from pathlib import Path
from typing import Any, Optional, Tuple

import serial
from loguru import logger

from backend.core.phone_cid import normalize_cid_value
from backend.voice.audio_utils import pcm_chunk_peak, wav_matches_modem_profile, wav_path_to_modem_pcm
from backend.voice.modem_profile import (
    CONEXANT_VOICE_PROFILE,
    USR_FALLBACK_PROFILE,
    USR_VOICE_PROFILE,
    ModemVoiceProfile,
    resolve_voice_profile,
)

# Mode voix (callattendant) : commandes AT pour jouer vers la ligne
# Voir https://github.com/emxsys/callattendant (Bruce Schubert / emxsys)
_VOICE_MODE = "AT+FCLASS=8"
_VSD_DISABLE_USR = "AT+VSD=128,0"       # desactive detection silence (USR 5637)
_VSD_DISABLE_CONEXANT = "AT+VSD=0,0"   # desactive detection silence (Zoom 3095 / Conexant)
_VOICE_COMPRESSION_USR = USR_VOICE_PROFILE.vsm_command
_VOICE_COMPRESSION_USR_FALLBACK = USR_FALLBACK_PROFILE.vsm_command
_VOICE_COMPRESSION_CONEXANT = CONEXANT_VOICE_PROFILE.vsm_command
_TAD_OFF_HOOK = "AT+VLS=1"
_VOICE_TX = "AT+VTX"
_VOICE_RX = "AT+VRX"
_DLE = 0x10
_DTE_END_VOICE_TX = (chr(16) + chr(3)).encode()  # DLE ETX (USR)
_DTE_END_VOICE_TX_CONEXANT = (chr(16) * 3 + chr(3)).encode()   # DLE DLE DLE ETX (Conexant)
_DTE_END_VOICE_RX_CONEXANT = (chr(16) * 3 + chr(33)).encode()   # DLE DLE DLE ! (Conexant)
_VRX_SAMPLE_RATE = USR_VOICE_PROFILE.sample_rate
_VRX_BYTES_PER_SEC = USR_VOICE_PROFILE.bytes_per_sec
_EXPECTED_FIRMWARE_HINT = "1.2.23"
# Perception de ligne (preemption) : poll serie et attente reponse modem au RING.
_MODEM_FAST_POLL_SEC = 0.005
_MONITOR_SERIAL_TIMEOUT_SEC = 0.005
_PREEMPT_AT_TIMEOUT_ATA_SEC = 0.40
_PREEMPT_AT_TIMEOUT_VOICE_SEC = 0.18


def _firmware_indicates_usr5637(firmware_ati3: Optional[str]) -> bool:
    """
    True si ATI3 correspond a un USR5637 (meme si ATI mentionne Conexant chipset).

    @param firmware_ati3 Reponse brute ATI3.
    @returns True pour U.S. Robotics / USR5637.
    """
    fw = (firmware_ati3 or "").upper()
    return any(token in fw for token in ("ROBOTICS", "USR", "5637", "56K FAX"))


def _detect_is_conexant_zoom(
    response_ati: bytes,
    response_ati0: bytes,
    firmware_ati3: Optional[str],
) -> bool:
    """
    Distingue Zoom/Conexant pur du USR5637 (chipset Conexant mais VSM USR).

    @param response_ati Reponses ATI / ATI0.
    @param response_ati0 Reponse ATI0.
    @param firmware_ati3 Firmware ATI3.
    @returns True uniquement pour modems style Zoom 3095 (VSM 1,8000,0,0).
    """
    if _firmware_indicates_usr5637(firmware_ati3):
        return False
    combined = (response_ati or b"") + (response_ati0 or b"")
    upper = combined.upper()
    return bool(
        combined
        and (
            b"CONEXANT" in upper
            or b"ZOOM" in upper
            or b"3095" in upper
        )
    )


def extract_incoming_dtmf_digit(line_str: str) -> Optional[str]:
    """
    Extrait une touche DTMF d'une ligne modem (URC ou chiffre isole).

    @param line_str Ligne decodee du port serie.
    @returns Touche normalisee (0-9, *, #, A-D) ou None.
    """
    s = (line_str or "").strip()
    if not s or s.upper() in ("OK", "ERROR", "CONNECT", "NO CARRIER"):
        return None
    if re.fullmatch(r"[\d*#A-Da-d]", s):
        return s.upper()
    m = re.search(r'(?:DTMF|VTD|\+VTD)[:\s=]+["\']?([\d*#A-D])', s, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None


def _escape_dle_pcm(data: bytes) -> bytes:
    """
    Double les octets DLE (0x10) dans le PCM pour le mode transparent V.253.

    @param data PCM 8-bit brut.
    @returns PCM safe pour VTX.
    """
    if not data or _DLE not in data:
        return data
    out = bytearray()
    for b in data:
        out.append(b)
        if b == _DLE:
            out.append(_DLE)
    return bytes(out)


# Delai minimum apres ouverture VRX avant detection raccrochage (settle ligne, pas 2s).
_VRX_MIN_HANGUP_GRACE_SEC = 0.4


def _vrx_text_has_hangup_marker(blob: bytes) -> bool:
    """
    Marqueurs AT texte dans le flux serie (hors PCM transparent).

    @param blob Buffer ASCII recent du flux VRX.
    @returns True si fin d'appel probable.
    """
    if not blob:
        return False
    u = blob.upper()
    return (
        b"NO CARRIER" in u
        or b"NO ANSWER" in u
        or b"NO DIALTONE" in u
        or b"NO DIAL TONE" in u
    )


def _vrx_dle_control_has_hangup_marker(blob: bytes) -> bool:
    """
    Marqueurs DLE V.253 (buffer controle uniquement, pas du PCM brut).

    USR5637 : DLE-h = raccrochage, DLE-E / DLE ETX = fin de session voix.
    DLE-s (silence modem) n'est PAS un raccrochage : ca coupe les messages trop tot.

    @param blob Suite de paires DLE+code extraites du flux VRX.
    @returns True si fin de session voix / raccrochage.
    """
    if not blob:
        return False
    return (
        b"\x10\x10\x10!" in blob
        or b"\x10\x10\x10\x03" in blob
        or b"\x10\x03" in blob
        or b"\x10!" in blob
        or b"\x10h" in blob
        or b"\x10H" in blob
    )


def _vrx_buffer_has_hangup_marker(blob: bytes) -> bool:
    """
    Compat tests : texte AT ou controle DLE sur un buffer deja filtre.

    @param blob Donnees a analyser.
    @returns True si marqueur de fin de ligne detecte.
    """
    return _vrx_text_has_hangup_marker(blob) or _vrx_dle_control_has_hangup_marker(blob)


class _VrxHangupScanner:
    """
    Analyse le flux VRX transparent en respectant l'echappement DLE-DLE.

    Evite les faux positifs quand du PCM brut contient 0x10 suivi d'un octet
    qui ressemble a un code de controle (ex. \\x10s).
    """

    def __init__(self) -> None:
        self._dle_pending = False
        self._control_tail = bytearray()
        self._text_tail = bytearray()

    def feed(self, raw: bytes) -> bool:
        """
        Ingere un bloc VRX et detecte un raccrochage distant.

        @param raw Octets lus sur le port serie.
        @returns True si un marqueur de fin de ligne est confirme.
        """
        if not raw:
            return False
        for b in raw:
            if self._dle_pending:
                self._dle_pending = False
                if b == _DLE:
                    continue
                self._control_tail.extend((_DLE, b))
                if len(self._control_tail) > 256:
                    del self._control_tail[:-256]
                if _vrx_dle_control_has_hangup_marker(bytes(self._control_tail)):
                    return True
                continue
            if b == _DLE:
                self._dle_pending = True
                continue
            if 32 <= b <= 126:
                self._text_tail.append(b)
                if len(self._text_tail) > 512:
                    del self._text_tail[:-512]
                if _vrx_text_has_hangup_marker(bytes(self._text_tail)):
                    return True
        return False


def _goertzel_power(samples: list[float], freq: float, sample_rate: int) -> float:
    """
    Puissance Goertzel normalisee sur une fenetre (ex. 440 Hz occupation FR).

    @param samples Echantillons flottants centres ~[-1, 1].
    @param freq Frequence cible Hz.
    @param sample_rate Taux d'echantillonnage.
    @returns Puissance relative (sans unite).
    """
    n = len(samples)
    if n < 8 or sample_rate <= 0:
        return 0.0
    w = 2.0 * math.pi * float(freq) / float(sample_rate)
    coeff = 2.0 * math.cos(w)
    s0 = 0.0
    s1 = 0.0
    s2 = 0.0
    for x in samples:
        s0 = float(x) + coeff * s1 - s2
        s2 = s1
        s1 = s0
    power = s1 * s1 + s2 * s2 - coeff * s1 * s2
    return power / float(n)


def _pcm_frame_to_floats(raw: bytes, *, sample_width: int) -> list[float]:
    """
    Convertit une fenetre PCM en flottants centres.

    @param raw Octets PCM.
    @param sample_width 1 = u8, 2 = s16le.
    @returns Liste de flottants ~[-1, 1].
    """
    width = max(1, int(sample_width))
    if width <= 1:
        return [(b - 128) / 128.0 for b in raw]
    out: list[float] = []
    for i in range(0, len(raw) - 1, 2):
        val = int.from_bytes(raw[i : i + 2], "little", signed=True)
        out.append(val / 32768.0)
    return out


class _VrxDisconnectToneScanner:
    """
    Detecte la tonalite d'occupation / bips de fin d'appel.

    Priorite : cadence 440 Hz (occupation FR, ~0,5 s on/off). Les lectures
    serie grosses sont decoupees en fenetres ~20 ms. ``trim_sec`` indique
    combien couper en fin de WAV. ``heard_speech`` = son non-tonal trop long.
    """

    def __init__(
        self,
        *,
        threshold: int,
        min_beeps: int = 3,
        sample_rate: int = 8000,
        min_pre_silence_sec: float = 0.25,
        min_burst_sec: float = 0.25,
        max_burst_sec: float = 0.75,
        min_gap_sec: float = 0.25,
        max_gap_sec: float = 0.85,
        tone_freq: float = 440.0,
        tone_power_min: float = 3.5,
    ) -> None:
        self._threshold = max(1, int(threshold))
        self._min_beeps = max(2, int(min_beeps))
        self._sample_rate = max(1000, int(sample_rate))
        self._min_pre_silence_sec = min_pre_silence_sec
        self._min_burst_sec = min_burst_sec
        self._max_burst_sec = max_burst_sec
        self._min_gap_sec = min_gap_sec
        self._max_gap_sec = max_gap_sec
        self._tone_freq = float(tone_freq)
        self._tone_power_min = float(tone_power_min)
        self._armed = False
        self._beeps = 0
        self._loud_sec = 0.0
        self._quiet_sec = 0.0
        self._gap_sec = 0.0
        self._seq_sec = 0.0
        self.trim_sec = 0.0
        self.heard_speech = False
        self._pending = b""
        self._nontone_loud_sec = 0.0

    def _reset_sequence(self) -> None:
        """Oublie la cadence en cours (parole ou trop d'ecart)."""
        self._beeps = 0
        self._seq_sec = 0.0
        self.trim_sec = 0.0

    @property
    def in_beep_train(self) -> bool:
        """True si on est dans une suite de bips / tonalite (pas de la parole)."""
        return self._beeps > 0 or (0 < self._loud_sec <= self._max_burst_sec)

    def feed(self, raw: bytes, *, sample_width: int) -> bool:
        """
        Ingere un bloc VRX et cherche une cadence d'occupation / bips.

        @param raw Octets PCM du flux VRX.
        @param sample_width 1 = u8, 2 = s16le.
        @returns True si assez de cycles consecutifs apres silence.
        """
        if not raw:
            return False
        width = max(1, int(sample_width))
        frame_samples = max(1, int(round(self._sample_rate * 0.04)))
        frame_bytes = frame_samples * width
        if self._pending:
            raw = self._pending + raw
            self._pending = b""
        rem = len(raw) % width
        if rem:
            self._pending = raw[-rem:]
            raw = raw[:-rem]
        if not raw:
            return False
        for off in range(0, len(raw), frame_bytes):
            frame = raw[off : off + frame_bytes]
            if len(frame) < width:
                break
            if self._feed_frame(frame, sample_width=width):
                return True
        return False

    def _feed_frame(self, raw: bytes, *, sample_width: int) -> bool:
        """
        Analyse une petite fenetre PCM (~40 ms) via Goertzel 440 Hz.

        @param raw Octets d'une fenetre.
        @param sample_width Largeur echantillon.
        @returns True si cadence de tonalite confirmee.
        """
        n_samples = len(raw) // max(1, int(sample_width))
        dur = n_samples / float(self._sample_rate)
        if dur <= 0:
            return False
        samples = _pcm_frame_to_floats(raw, sample_width=sample_width)
        tone_power = _goertzel_power(samples, self._tone_freq, self._sample_rate)
        peak = pcm_chunk_peak(raw, sample_width=sample_width)
        soft_peak = max(8, self._threshold // 2)
        is_tone = tone_power >= self._tone_power_min and peak >= soft_peak
        # Hysteresis debut/fin : fenetres de bord encore un peu 440 Hz.
        if (
            not is_tone
            and peak >= soft_peak
            and tone_power >= self._tone_power_min * 0.35
            and (self._loud_sec > 0 or self._gap_sec > 0 or self._beeps > 0)
        ):
            is_tone = True
        # Debut du bip suivant : attaque forte pendant un gap valide (Goertzel
        # encore bas sur 1 frame, ex. tonalite FR reelle).
        if (
            not is_tone
            and self._loud_sec <= 0
            and self._beeps > 0
            and peak >= soft_peak
            and self._min_gap_sec <= self._gap_sec <= self._max_gap_sec
        ):
            is_tone = True
        if is_tone:
            self._quiet_sec = 0.0
            self._nontone_loud_sec = 0.0
            self._loud_sec += dur
            if self._loud_sec > self._max_burst_sec:
                self._reset_sequence()
                self._armed = False
                self._gap_sec = 0.0
                self._loud_sec = 0.0
            return False
        # Fin de tonalite : une fenetre de bord encore un peu forte ne doit
        # pas casser le cycle (peak residuel, Goertzel deja bas).
        if self._loud_sec > 0:
            burst = self._loud_sec
            gap = self._gap_sec
            self._loud_sec = 0.0
            self._gap_sec = 0.0
            self._nontone_loud_sec = 0.0
            short_ok = self._min_burst_sec <= burst <= self._max_burst_sec
            gap_ok = self._beeps == 0 or (self._min_gap_sec <= gap <= self._max_gap_sec)
            if self._armed and short_ok and gap_ok:
                self._beeps += 1
                self._seq_sec = burst if self._beeps == 1 else self._seq_sec + gap + burst
                self.trim_sec = self._seq_sec
                if self._beeps >= self._min_beeps:
                    return True
            else:
                self._reset_sequence()
        if peak >= self._threshold:
            self._quiet_sec = 0.0
            self._nontone_loud_sec += dur
            # Ne raz le gap que si aucune cadence n'est en cours.
            if self._beeps == 0 and tone_power < self._tone_power_min * 0.15:
                self._gap_sec = 0.0
            if self._nontone_loud_sec >= 0.20:
                self.heard_speech = True
                self._armed = False
                self._reset_sequence()
            return False
        self._nontone_loud_sec = 0.0
        self._quiet_sec += dur
        self._gap_sec += dur
        if self._quiet_sec >= self._min_pre_silence_sec:
            self._armed = True
        if self._beeps > 0 and self._gap_sec > self._max_gap_sec:
            self._reset_sequence()
        return False


# Alias et helpers exposes pour tests sans materiel (scripts/modem_lab/tests/test_modem_handler_smoke.py).
_vrx_stream_contains_hangup_marker = _vrx_buffer_has_hangup_marker


def _trim_pcm_tail(
    data: bytes,
    *,
    sample_width: int,
    sample_rate: int,
    trim_sec: float,
) -> bytes:
    """
    Retire une queue PCM (bips de raccrochage) sans vider tout le message.

    @param data PCM brut.
    @param sample_width Octets par echantillon.
    @param sample_rate Taux Hz.
    @param trim_sec Duree a couper en fin de fichier.
    @returns PCM tronque.
    """
    if not data or trim_sec <= 0:
        return data
    width = max(1, int(sample_width))
    rate = max(1000, int(sample_rate))
    nbytes = int(trim_sec * rate) * width
    if nbytes <= 0:
        return data
    keep = len(data) - nbytes
    if keep < width * 400:
        keep = min(len(data), width * 400)
    keep -= keep % width
    return data[: max(0, keep)]


def _scan_hangup_tone_trim(
    data: bytes,
    *,
    sample_width: int,
    sample_rate: int,
    threshold: int,
) -> float:
    """
    Cherche une tonalite de fin dans le PCM et renvoie la duree a couper.

    Utile en filet de securite si l'arret live est tombe sur silence
    alors que la queue contient encore les bips operateur.

    @param data PCM enregistre.
    @param sample_width Largeur echantillon.
    @param sample_rate Taux Hz.
    @param threshold Seuil peak (meme echelle que pcm_chunk_peak).
    @returns Secondes a retirer en fin, ou 0.
    """
    if not data:
        return 0.0
    scanner = _VrxDisconnectToneScanner(
        threshold=threshold,
        sample_rate=sample_rate,
        min_beeps=3,
    )
    # Gros blocs volontairement : feed() decoupe en 20 ms.
    step = max(sample_width, int(sample_rate * sample_width * 0.5))
    for i in range(0, len(data), step):
        if scanner.feed(data[i : i + step], sample_width=sample_width):
            # Ne coupe que si la cadence est en queue (fin d'appel).
            consumed = i + step
            remain = len(data) - consumed
            remain_sec = remain / float(max(1, sample_rate * sample_width))
            if remain_sec <= 8.0:
                # Inclure aussi le silence / bips encore presents apres le hit.
                return float(scanner.trim_sec) + max(0.0, remain_sec)
            # Faux positif en milieu de message : on continue apres reset.
            scanner = _VrxDisconnectToneScanner(
                threshold=threshold,
                sample_rate=sample_rate,
                min_beeps=3,
            )
    return 0.0


def _serial_buffer_shows_remote_pickup(blob: bytes) -> bool:
    """Indice série de décroché distant : DLE+a (answer tone) ou réponse VCON."""
    if not blob:
        return False
    if b"\x10a" in blob:
        return True
    return b"VCON" in blob.upper()


def _response_has_numeric_at_result(raw: bytes, allowed: tuple[int, ...]) -> bool:
    """True si une ligne du buffer est un entier exactement égal à un code AT résultat autorisé."""
    text = raw.decode("utf-8", errors="ignore").replace("\r\n", "\n")
    for line in text.split("\n"):
        s = line.strip()
        if s.isdigit() and int(s) in allowed:
            return True
    return False


class ModemHandler:
    """Gère la communication avec le modem"""
    
    def __init__(self, port: Optional[str] = None, baudrate: int = 115200):
        """
        Initialise le gestionnaire de modem
        
        Args:
            port: Port série du modem (auto-détection si None)
            baudrate: Vitesse de communication
        """
        self.port = port
        self.baudrate = baudrate
        self.serial_connection: Optional[serial.Serial] = None
        self.is_initialized = False
        self._is_conexant = False  # True si modem Conexant (Zoom 3095, etc.)
        self.preferred_vsm: Optional[str] = None
        self.voice_profile: ModemVoiceProfile = USR_VOICE_PROFILE
        self.on_incoming_call: Optional[callable] = None  # Callback pour les appels entrants
        self._serial_io_lock = asyncio.Lock()
        self._serial_sync_lock = threading.RLock()
        self._outgoing_owns_serial = False
        self._vrx_saved_timeout: Optional[float] = None
        # True pendant AT+VTX (talkspurt micro) : pas de lecture VRX.
        self._vtx_active = False
        # Demande d'arret urgent (raccrochage UI) : coupe les ecritures VTX pacees.
        self._voice_abort = False
        # Diagnostics sante / CID (exposes via /health).
        self.firmware_ati3: Optional[str] = None
        self.last_ring_at: Optional[float] = None
        self.last_cid_raw: Optional[str] = None
        self.last_error: Optional[str] = None
        # Gains voix optionnels (None = ne pas envoyer la commande).
        self.voice_vgr: Optional[int] = None
        self.voice_vgt: Optional[int] = None
        self.modem_country_gci: Optional[str] = None
        self.enable_distinctive_ring: bool = False
        self.enable_pcw_off_for_cid: bool = True
        # Coupe playback si evenement parallele / hangup detecte pendant VTX.
        self._playback_interrupted = False
        # Ignore les fausses coupures (RING suivant, restes RX) pendant l'accueil.
        self._vtx_ignore_interrupt_until: float = 0.0
        # Perception de ligne (rings=0) : decrochage immediat au RING pour battre messagerie SFR.
        self.line_preempt_on_ring = False
        self._line_preempt_active = False
        self._line_preempt_ok = False
        self._preempt_voice_setup_pending = False
        self._deferred_preempt_task: Optional[asyncio.Task] = None
        self.last_line_preempt_at: Optional[float] = None
        self.last_line_preempt_reason: Optional[str] = None
        self.last_line_preempt_ms: Optional[int] = None
        # Alias historique (seize) — conserve pour compat config / logs.
        self._incoming_line_seized = False
        self._incoming_seize_ok = False
        self._voice_line_ready = False
        self._deferred_seize_task: Optional[asyncio.Task] = None
        # Accueil immediat post-seize (style Call Attendant) : WAV pre-cache + tache asyncio.
        self.early_greeting_wav: Optional[Path] = None
        self.early_greeting_enabled: bool = False
        self._greeting_played_on_seize: bool = False
        self._early_greeting_task: Optional[asyncio.Task] = None
        self._early_greeting_pending: bool = False
        # Raison du dernier arret VRX (hangup_marker, silence, timeout, ...).
        self.last_vrx_stop_reason: Optional[str] = None
        self.last_vrx_heard_speech: bool = False
        self._vtx_event_scanner: Optional[_VrxHangupScanner] = None
        # Secondes max apres RING avant VLS=1 (laisse passer NMBR= ETSI).
        self.instant_seize_cid_grace_sec: float = 0.35
        # Attente DTMF entrant (gate anti-robots).
        self._dtmf_wait_expected: Optional[str] = None
        self._dtmf_last_digit: Optional[str] = None
        self._dtmf_event: Optional[asyncio.Event] = None
        self._modem_sync_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="modem_sync",
        )

    async def run_modem_sync(self, fn, *args, timeout: float = 3.0):
        """
        Execute une operation serie synchrone sur un seul thread dedie.

        Evite la saturation du pool asyncio par des ATH/VRX bloques en parallele.

        @param fn Callable synchrone (methode modem).
        @param args Arguments positionnels pour fn.
        @param timeout Delai max secondes.
        @returns Valeur retournee par fn.
        @raises asyncio.TimeoutError Si l'operation depasse timeout (reset port en secours).
        """
        loop = asyncio.get_running_loop()
        if args:
            call = partial(fn, *args)
        else:
            call = fn
        fut = loop.run_in_executor(self._modem_sync_executor, call)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("[MODEM] run_modem_sync timeout ({:.1f}s) — reset port", timeout)
            threading.Thread(target=self._force_serial_reset_sync, daemon=True).start()
            raise

    async def detect_modem(self) -> Optional[str]:
        """
        Détecte automatiquement le port du modem
        
        Returns:
            Chemin du port série détecté ou None
        """
        import serial.tools.list_ports
        
        logger.info("Recherche du modem...")
        
        # Ports communs pour les modems USB
        common_ports = ['/dev/ttyACM0', '/dev/ttyUSB0', '/dev/ttyUSB1']
        
        # Vérifier les ports communs
        for port in common_ports:
            if Path(port).exists():
                logger.info(f"Port trouvé: {port}")
                return port
        
        # Lister tous les ports série disponibles
        ports = serial.tools.list_ports.comports()
        for port_info in ports:
            port_path = port_info.device
            logger.debug(f"Port série disponible: {port_path}")
            
            # Essayer de se connecter pour vérifier si c'est un modem
            try:
                test_serial = serial.Serial(port_path, self.baudrate, timeout=1)
                test_serial.write(b'AT\r\n')
                response = test_serial.read(100)
                test_serial.close()
                
                if b'OK' in response:
                    logger.info(f"Modem détecté sur {port_path}")
                    return port_path
            except Exception as e:
                logger.debug(f"Erreur lors du test de {port_path}: {e}")
                continue
        
        logger.warning("Aucun modem détecté")
        return None
    
    async def initialize(self) -> bool:
        """
        Initialise la connexion au modem
        
        Returns:
            True si l'initialisation réussit
        """
        try:
            # Détecter le port si non spécifié
            if not self.port:
                self.port = await self.detect_modem()
                if not self.port:
                    logger.error("Impossible de détecter le modem")
                    return False
            
            # Ouvrir la connexion série
            logger.info(f"Connexion au modem sur {self.port}")
            self.serial_connection = serial.Serial(
                self.port,
                self.baudrate,
                timeout=1,
                write_timeout=1
            )
            
            # Attendre que le modem soit prêt
            await asyncio.sleep(1)
            
            # Envoyer des commandes AT pour initialiser
            await self.send_command("AT")
            await self.send_command("ATE0")  # Desactiver l'echo
            await self.send_command("AT+FCLASS=0")  # Mode data : indispensable pour recevoir RING
            if self.enable_pcw_off_for_cid:
                # Call Waiting off aide parfois le CID formate (retours USR / communautaires).
                r_pcw = await self.send_command_full("AT+PCW=0", timeout=2.0)
                logger.info(
                    "Modem AT+PCW=0 -> {}",
                    (r_pcw or b"").decode("utf-8", errors="ignore").strip().replace("\r\n", " | ") or "(vide)",
                )
            await self.send_command("AT+VCID=1")  # Activer le Caller ID
            if self.enable_distinctive_ring:
                await self.send_command_full("AT+VDR=1,0", timeout=2.0)
            if self.modem_country_gci:
                gci = str(self.modem_country_gci).strip().upper().lstrip("0X")
                await self.send_command_full(f"AT+GCI={gci}", timeout=2.0)

            # Type de modem : Conexant / USR 5637 = mode voix serie supporté
            response_ati = await self.send_command_full("ATI", timeout=2.0)
            response_ati0 = await self.send_command_full("ATI0", timeout=2.0)
            response_ati3 = await self.send_command_full("ATI3", timeout=2.0)
            self.firmware_ati3 = (
                (response_ati3 or b"").decode("utf-8", errors="ignore").strip().replace("\r\n", " ")
                or None
            )
            if self.firmware_ati3:
                logger.info("Modem ATI3 (firmware): {}", self.firmware_ati3)
                if _EXPECTED_FIRMWARE_HINT not in self.firmware_ati3:
                    logger.warning(
                        "Firmware modem ({}) hors hint {} — CID / voix peuvent etre foireux",
                        self.firmware_ati3,
                        _EXPECTED_FIRMWARE_HINT,
                    )
            combined = (response_ati or b"") + (response_ati0 or b"")
            self._is_conexant = _detect_is_conexant_zoom(
                response_ati or b"",
                response_ati0 or b"",
                self.firmware_ati3,
            )
            if self._is_conexant:
                logger.info("Modem Conexant/Zoom detecte (mode voix serie 8 kHz u8)")
            elif _firmware_indicates_usr5637(self.firmware_ati3):
                logger.info("Modem USR5637 detecte (mode voix serie 11 kHz s16)")
            else:
                logger.info(
                    "Modem detecte (type non identifie). Reponses ATI: {}",
                    combined.decode("utf-8", errors="ignore").strip() or "(vide)",
                )
            self.voice_profile = resolve_voice_profile(
                is_conexant=self._is_conexant,
                vsm_spec=self.preferred_vsm,
            )
            logger.info(
                "Profil voix modem: {} ({}, {} Hz, {}-bit, {})",
                self.voice_profile.name,
                self.voice_profile.vsm_command,
                self.voice_profile.sample_rate,
                self.voice_profile.sample_width * 8,
                self.voice_profile.ffmpeg_codec,
            )

            self.is_initialized = True
            self.last_error = None
            logger.info("Modem initialisé avec succès")
            return True

        except Exception as e:
            # Pas de traceback complet : erreur courante en dev (mauvais port, OS sans /dev/ttyACM0).
            self.last_error = str(e)
            logger.warning(
                "Modem indisponible sur {} — verifier MODEM_PORT ou laisser vide pour auto-detect: {}",
                self.port,
                e,
            )
            return False

    def _close_serial(self) -> None:
        """Ferme le port série sans toucher à is_initialized ni port/baudrate."""
        if self.serial_connection:
            try:
                if self.serial_connection.is_open:
                    self.serial_connection.close()
            except (OSError, serial.SerialException):
                pass
            self.serial_connection = None

    def _close_serial_unsafe(self) -> None:
        """Ferme le port sans verrou (debloque un thread sync bloque en lecture)."""
        conn = self.serial_connection
        self.serial_connection = None
        if conn:
            try:
                if conn.is_open:
                    conn.close()
            except (OSError, serial.SerialException):
                pass

    def _force_serial_reset_sync(self) -> None:
        """
        Coupe le port serie sans ATH (debloque un hangup sync ou thread orphelin).

        @returns None
        """
        self._voice_abort = True
        self._vtx_active = False
        self._close_serial_unsafe()
        self._reset_voice_session_flags()
        self.log_voice_session("force_serial_reset")

    def _fast_cleanup_after_remote_hangup_sync(self) -> bool:
        """
        Remet le modem on-hook et en mode data apres un appel.

        Important USR5637 : ``AT+FCLASS=0`` seul NE raccroche PAS si on est
        encore en voix (AT+VLS=1). Il faut ATH / ATH0, sinon la ligne reste OQP.

        @returns True si ATH ou FCLASS a repondu OK.
        """
        self._voice_abort = True
        self.log_voice_session("fast_cleanup_debut")
        if not self.serial_connection or not self.serial_connection.is_open:
            self._reset_voice_session_flags()
            self.log_voice_session("fast_cleanup_ok", port=0)
            return True
        try:
            if self._vtx_active:
                end_seq = _DTE_END_VOICE_TX_CONEXANT if self._is_conexant else _DTE_END_VOICE_TX
                try:
                    self.serial_connection.write(end_seq)
                    self.serial_connection.flush()
                    time.sleep(0.05)
                except (OSError, serial.SerialException):
                    pass
                self._vtx_active = False
            try:
                self._vrx_transparent_close_sync()
            except Exception:
                pass
            self._flush_serial_rx_sync(max_sec=0.2)

            ath_ok = False
            for cmd in ("ATH", "ATH0"):
                try:
                    self.serial_connection.write(f"{cmd}\r\n".encode())
                    self.serial_connection.flush()
                    deadline = time.monotonic() + 1.5
                    buf = b""
                    while time.monotonic() < deadline:
                        if self.serial_connection.in_waiting > 0:
                            buf += self.serial_connection.read(
                                min(256, self.serial_connection.in_waiting)
                            )
                            if b"OK" in buf or b"ERROR" in buf:
                                break
                        time.sleep(0.05)
                    if b"OK" in buf:
                        ath_ok = True
                        break
                except (OSError, serial.SerialException) as exc:
                    logger.warning("[MODEM] fast_cleanup {}: {}", cmd, exc)
                    break

            fclass_ok = self._send_command_sync("AT+FCLASS=0", timeout=1.0)
            self._send_command_sync("AT+VCID=1", timeout=1.0)
            self._incoming_line_seized = False
            self._incoming_seize_ok = False
            self._reset_voice_session_flags()
            ok = bool(ath_ok or fclass_ok)
            self.log_voice_session(
                "fast_cleanup_ok",
                ath=int(ath_ok),
                fclass=int(bool(fclass_ok)),
            )
            if not ath_ok:
                logger.warning(
                    "[MODEM] fast_cleanup sans ATH OK — risque ligne OQP (fclass={})",
                    int(bool(fclass_ok)),
                )
            return ok
        except (OSError, serial.SerialException) as exc:
            logger.warning("[MODEM] fast_cleanup: {}", exc)
            self._close_serial_unsafe()
            self._reset_voice_session_flags()
            return False

    async def reconnect(self, *, attempts: int = 6) -> bool:
        """
        Ferme et rouvre le port série après une erreur I/O (EIO).
        Réapplique les commandes AT minimales (AT, ATE0, AT+VCID=1).
        Retourne True si la reconnexion a réussi.

        @param attempts Nombre de tentatives (reset USB peut prendre quelques secondes).
        """
        from pathlib import Path

        last_error: Optional[Exception] = None
        for attempt in range(max(1, attempts)):
            async with self._serial_io_lock:
                self._close_serial()
            try:
                await asyncio.sleep(0.4 + 0.35 * attempt)
                port = self.port
                if not port or not Path(port).exists():
                    detected = await self.detect_modem()
                    if not detected:
                        logger.warning(
                            "Modem reconnexion: aucun port serie (tentative {}/{})",
                            attempt + 1,
                            attempts,
                        )
                        continue
                    logger.info("Modem reconnexion: port mis a jour {} -> {}", port, detected)
                    self.port = detected
                    port = detected
                async with self._serial_io_lock:
                    self.serial_connection = serial.Serial(
                        port,
                        self.baudrate,
                        timeout=1,
                        write_timeout=1,
                    )
                await asyncio.sleep(0.6)
                await self.send_command("AT", _retry=False)
                await self.send_command("ATE0", _retry=False)
                # On-hook avant FCLASS : evite ligne OQP apres seize voix.
                try:
                    await self.send_command("ATH", _retry=False)
                except Exception:
                    pass
                try:
                    await self.send_command("ATH0", _retry=False)
                except Exception:
                    pass
                await self.send_command("AT+FCLASS=0", _retry=False)
                await self.send_command("AT+VCID=1", _retry=False)
                try:
                    async with self._serial_io_lock:
                        if self.serial_connection and self.serial_connection.is_open:
                            self.serial_connection.timeout = 0.05
                except (OSError, serial.SerialException):
                    pass
                logger.info("Modem reconnexion reussie sur {}", self.port)
                return True
            except Exception as e:
                last_error = e
                logger.warning(
                    "Modem reconnexion echouee (tentative {}/{}): {}",
                    attempt + 1,
                    attempts,
                    e,
                )
                async with self._serial_io_lock:
                    self._close_serial()
        if last_error:
            logger.warning("Modem reconnexion abandonnee: {}", last_error)
        return False
    
    async def send_command(self, command: str, timeout: float = 2.0, _retry: bool = True) -> bytes:
        """
        Envoie une commande AT au modem et lit jusqu'au premier CRLF.
        Pour ATA ou commandes lentes, preferer send_command_full.
        En cas d'erreur I/O (EIO), tente une reconnexion et un seul retry.
        """
        try:
            async with self._serial_io_lock:
                return await self._send_command_unlocked(command, timeout)
        except (OSError, serial.SerialException) as e:
            if _retry and (getattr(e, "errno", None) == errno.EIO or isinstance(e, serial.SerialException)):
                logger.warning("Erreur port sur commande {} ({}), reconnexion puis retry", command, e)
                if await self.reconnect():
                    return await self.send_command(command, timeout, _retry=False)
            logger.error("Erreur envoi commande {}: {}", command, e)
            raise
        except Exception as e:
            logger.error("Erreur envoi commande {}: {}", command, e)
            raise

    async def _send_command_unlocked(self, command: str, timeout: float = 2.0) -> bytes:
        if not self.serial_connection or not self.serial_connection.is_open:
            raise RuntimeError("Modem non connecté")
        self.serial_connection.write(f"{command}\r\n".encode())
        response = b""
        start = time.monotonic()
        while (time.monotonic() - start) < timeout:
            if self.serial_connection.in_waiting > 0:
                response += self.serial_connection.read(self.serial_connection.in_waiting)
                if b"\r\n" in response:
                    break
            await asyncio.sleep(0.1)
        logger.debug("Commande: {} -> Reponse: {}", command, response.decode("utf-8", errors="ignore"))
        return response

    async def send_command_full(
        self, command: str, timeout: float = 5.0, stop_on_ring: bool = True, _retry: bool = True
    ) -> bytes:
        """
        Envoie une commande AT et lit toute la reponse jusqu'a un code resultat ou timeout.
        Pour ATA, passer stop_on_ring=False pour ne pas s'arreter sur RING (le modem envoie
        souvent DATE/NMBR/NAME/RING avant OK ou CONNECT).
        En cas d'erreur I/O (EIO), tente une reconnexion et un seul retry.
        """
        try:
            async with self._serial_io_lock:
                return await self._send_command_full_unlocked(command, timeout, stop_on_ring)
        except (OSError, serial.SerialException) as e:
            if _retry and (getattr(e, "errno", None) == errno.EIO or isinstance(e, serial.SerialException)):
                logger.warning("Erreur port sur {} ({}), reconnexion puis retry", command, e)
                if await self.reconnect():
                    return await self.send_command_full(command, timeout, stop_on_ring, _retry=False)
            logger.error("Erreur send_command_full {}: {}", command, e)
            raise
        except Exception as e:
            logger.error("Erreur send_command_full {}: {}", command, e)
            raise

    async def _send_command_full_unlocked(
        self, command: str, timeout: float = 5.0, stop_on_ring: bool = True
    ) -> bytes:
        if not self.serial_connection or not self.serial_connection.is_open:
            raise RuntimeError("Modem non connecté")
        codes = (b"OK", b"ERROR", b"CONNECT", b"NO CARRIER")
        if stop_on_ring:
            codes = codes + (b"RING", b"BUSY")
        self.serial_connection.write(f"{command}\r\n".encode())
        self.serial_connection.flush()
        response = b""
        start = time.monotonic()
        while (time.monotonic() - start) < timeout:
            if self.serial_connection.in_waiting > 0:
                response += self.serial_connection.read(self.serial_connection.in_waiting)
            if any(code in response for code in codes):
                await asyncio.sleep(0.2)
                if self.serial_connection.in_waiting > 0:
                    response += self.serial_connection.read(self.serial_connection.in_waiting)
                break
            await asyncio.sleep(0.1)
        return response

    def _parse_caller_id_from_response(self, response: bytes) -> Tuple[Optional[str], Optional[str]]:
        """Extrait NMBR= et NAME= de la reponse modem (ex. reponse ATA avec Caller ID)."""
        text = response.decode("utf-8", errors="ignore")
        nmbr = re.search(r"NMBR\s*=\s*(\S+)", text, flags=re.IGNORECASE)
        name = re.search(r"NAME\s*=\s*([^\r\n]+)", text, flags=re.IGNORECASE)
        cid = normalize_cid_value(nmbr.group(1) if nmbr else None)
        cname = normalize_cid_value(name.group(1) if name else None)
        if nmbr and not cid:
            logger.info("Caller ID masque dans reponse ATA: NMBR={}", nmbr.group(1).strip())
        return (cid, cname)

    def health_snapshot(self) -> dict:
        """
        Etat modem pour /health (sans ouvrir le port).

        @returns Dict serialisable JSON.
        """
        return {
            "modem_initialized": bool(self.is_initialized),
            "modem_port": self.port,
            "firmware_ati3": self.firmware_ati3,
            "last_ring_at": self.last_ring_at,
            "last_cid_raw": self.last_cid_raw,
            "last_error": self.last_error,
            "vtx_active": bool(self._vtx_active),
            "outgoing_owns_serial": bool(self._outgoing_owns_serial),
            "voice_vsm": self.voice_profile.vsm_command,
            "voice_sample_rate": self.voice_profile.sample_rate,
            "voice_sample_width": self.voice_profile.sample_width,
            "modem_baudrate": self.baudrate,
        }

    def _flush_serial_rx_sync(self, max_sec: float = 0.12) -> None:
        """
        Vide le buffer RX serie (restes RING/CID/PCM apres VRX ou VTX).

        @param max_sec Duree max de drainage (plus long apres mode voix transparent).
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return
        try:
            deadline = time.monotonic() + max(0.02, float(max_sec))
            while time.monotonic() < deadline:
                try:
                    pending = self.serial_connection.in_waiting
                except (OSError, serial.SerialException):
                    break
                if pending <= 0:
                    time.sleep(0.01)
                    continue
                self.serial_connection.read(min(pending, 4096))
        except (OSError, serial.SerialException):
            pass

    def _configure_voice_after_seize_sync(self) -> None:
        """
        Prepare le modem pour VTX/VRX apres VLS=1 (VSD, VSM, gains).

        Sans VSM, le premier accueil peut etre muet ou echouer sur USR5637.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return
        try:
            vsd = _VSD_DISABLE_CONEXANT if self._is_conexant else _VSD_DISABLE_USR
            self._send_command_sync(vsd)
            self._apply_voice_gains_sync()
            self._apply_vsm_sync()
            self._voice_line_ready = True
        except Exception as exc:
            logger.debug("configure_voice_after_seize: {}", exc)

    async def prepare_voice_line_after_seize(self) -> None:
        """
        Apres seize sync au RING : purge RX + config voix avant l'accueil TTS.

        @returns None.
        """
        loop = asyncio.get_event_loop()
        async with self._serial_io_lock:
            await self.run_modem_sync(self._prepare_voice_line_after_seize_sync, timeout=5.0)

    def _prepare_voice_line_after_seize_sync(self) -> None:
        """Version synchrone de ``prepare_voice_line_after_seize`` (sous lock)."""
        self._flush_serial_rx_sync()
        self._configure_voice_after_seize_sync()

    def _apply_voice_gains_sync(self) -> None:
        """Envoie +VGR / +VGT si configures (apres FCLASS=8)."""
        if self.voice_vgr is not None:
            self._send_command_sync(f"AT+VGR={int(self.voice_vgr)}")
        if self.voice_vgt is not None:
            self._send_command_sync(f"AT+VGT={int(self.voice_vgt)}")

    def _apply_vsm_sync(self) -> bool:
        """
        Envoie AT+VSM du profil actif, avec fallback USR 8 kHz / 8-bit.

        @returns True si une commande VSM a ete acceptee.
        """
        cmd = self.voice_profile.vsm_command
        if self._send_command_sync(cmd):
            return True
        if self._is_conexant:
            ok = self._send_command_sync(_VOICE_COMPRESSION_CONEXANT)
            if ok:
                self.voice_profile = CONEXANT_VOICE_PROFILE
            return ok
        if cmd != _VOICE_COMPRESSION_USR_FALLBACK and self._send_command_sync(
            _VOICE_COMPRESSION_USR_FALLBACK
        ):
            logger.warning(
                "VSM {} refuse, fallback {}",
                cmd,
                _VOICE_COMPRESSION_USR_FALLBACK,
            )
            self.voice_profile = USR_FALLBACK_PROFILE
            return True
        logger.warning("VSM echoue: {}", cmd)
        return False

    def _peek_serial_interrupt_sync(self) -> bool:
        """
        Lit le buffer serie pendant VTX : hangup distant (pas les RING).

        @returns True si il faut couper le playback.
        """
        if time.monotonic() < self._vtx_ignore_interrupt_until:
            return False
        if not self.serial_connection or not self.serial_connection.is_open:
            return False
        try:
            if self.serial_connection.in_waiting <= 0:
                return False
            blob = self.serial_connection.read(min(self.serial_connection.in_waiting, 512))
        except (OSError, serial.SerialException):
            return False
        if not blob:
            return False
        return self._blob_means_vtx_hangup(blob)

    def _blob_means_vtx_hangup(self, blob: bytes) -> bool:
        """
        True si des octets RX pendant VTX indiquent un raccrochage (pas un RING).

        @param blob Donnees lues sur le port pendant l'accueil.
        @returns True pour couper VTX.
        """
        if not blob:
            return False
        upper = blob.upper()
        if b"RING" in upper:
            ring_only = upper.replace(b"RING", b"").replace(b"\r", b"").replace(b"\n", b"").strip()
            if not ring_only:
                return False
            blob = re.sub(rb"RING[\r\n]*", b"", blob, flags=re.IGNORECASE)
            if not blob.strip():
                return False
        scanner = self._vtx_event_scanner
        if scanner is None:
            scanner = _VrxHangupScanner()
            self._vtx_event_scanner = scanner
        if scanner.feed(blob) or _vrx_text_has_hangup_marker(blob):
            logger.info("Playback interrompu (raccrochage pendant VTX)")
            self._playback_interrupted = True
            self.last_vrx_stop_reason = "hangup_marker"
            return True
        if _serial_buffer_shows_remote_pickup(blob):
            logger.info("Playback interrompu (decroche parallele pendant VTX)")
            self._playback_interrupted = True
            return True
        return False

    def _drain_rx_check_hangup_sync(self) -> bool:
        """
        Vide le RX apres VTX et detecte un raccrochage arrive pendant l'accueil.

        @returns True si raccrochage distant vu dans le reliquat serie.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return bool(self._playback_interrupted)
        leftover = b""
        try:
            deadline = time.monotonic() + 0.25
            while time.monotonic() < deadline:
                pending = 0
                try:
                    pending = self.serial_connection.in_waiting
                except (OSError, serial.SerialException):
                    break
                if pending <= 0:
                    time.sleep(0.02)
                    continue
                leftover += self.serial_connection.read(min(pending, 1024))
        except (OSError, serial.SerialException):
            leftover = b""
        if leftover and self._blob_means_vtx_hangup(leftover):
            return True
        return bool(self._playback_interrupted)

    async def answer_call(self, fast_voice_seize: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Decroche l'appel entrant.
        Essaie ATA (reponse OK ou CONNECT), puis ATH1 (off-hook) si besoin.
        Si ``fast_voice_seize`` est True (rings=0 coupe-sonnerie), passe directement
        en mode voix AT+VLS=1 pour couper la sonnerie du fixe parallele plus vite.

        Retourne (succes, caller_id, caller_name) ; caller_id/name peuvent etre remplis
        si le modem envoie NMBR=/NAME= dans la reponse a ATA.
        """
        if fast_voice_seize and self.supports_voice_serial:
            return await self._answer_call_voice_seize()
        caller_id, caller_name = None, None
        try:
            # Ne pas s'arreter sur RING : le modem envoie souvent DATE/NMBR/NAME/RING puis OK ou CONNECT
            response = await self.send_command_full("ATA", timeout=8.0, stop_on_ring=False)
            raw = response.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ")
            logger.info("Modem ATA -> reponse brute: {}", raw or "(vide)")
            caller_id, caller_name = self._parse_caller_id_from_response(response)
            if b"OK" in response or b"CONNECT" in response:
                return (True, caller_id, caller_name)
            logger.warning("ATA sans OK/CONNECT, essai ATH1 (off-hook)...")
            response2 = await self.send_command_full("ATH1", timeout=5.0)
            raw2 = response2.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ")
            logger.info("Modem ATH1 -> reponse brute: {}", raw2 or "(vide)")
            if b"OK" in response2:
                return (True, caller_id, caller_name)
            # NO CARRIER = appel deja pris ailleurs (fixe parallele) ou raccroche :
            # ne jamais forcer AT+VLS=1 (sinon bip/accueil par-dessus la conversation).
            if b"NO CARRIER" in response2 or b"NO ANSWER" in response2 or b"BUSY" in response2:
                logger.warning(
                    "ATH1 indique ligne indisponible ({}) — abandon decrochage (pas de VLS=1)",
                    raw2 or "(vide)",
                )
                return (False, caller_id, caller_name)
            if self._is_conexant:
                logger.warning("ATH1 refuse, essai mode voix (AT+FCLASS=8 puis AT+VSD puis AT+VLS=1)...")
                r3 = await self.send_command_full(_VOICE_MODE, timeout=3.0)
                logger.info("Modem AT+FCLASS=8 -> {}", r3.decode("utf-8", errors="ignore").strip().replace("\r\n", " | "))
                if b"OK" in r3:
                    vsd = _VSD_DISABLE_CONEXANT if self._is_conexant else _VSD_DISABLE_USR
                    r_vsd = await self.send_command_full(vsd, timeout=2.0)
                    if b"OK" in r_vsd:
                        logger.debug("Modem {} -> OK", vsd)
                    r4 = await self.send_command_full(_TAD_OFF_HOOK, timeout=3.0)
                    logger.info("Modem AT+VLS=1 -> {}", r4.decode("utf-8", errors="ignore").strip().replace("\r\n", " | "))
                    if b"OK" in r4:
                        return (True, caller_id, caller_name)
            return (False, caller_id, caller_name)
        except Exception as e:
            logger.error("Erreur lors du decrochage: {}", e)
            return (False, None, None)

    async def _answer_call_voice_seize(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Decrochage rapide entrant : ATA operateur + mode voix (meme logique que seize sync).

        @returns Tuple (succes, caller_id, caller_name).
        """
        caller_id, caller_name = None, None
        if self._incoming_line_seized:
            return (bool(self._incoming_seize_ok), caller_id, caller_name)
        self._incoming_line_seized = True
        try:
            logger.info("Decrochage rapide entrant (ATA + mode voix)")
            loop = asyncio.get_event_loop()
            async with self._serial_io_lock:
                ok = await self.run_modem_sync(
                    lambda: self._voice_seize_sync_unlocked(fast=True),
                    timeout=6.0,
                )
            self._incoming_seize_ok = bool(ok)
            if not ok:
                logger.warning("Decrochage rapide echoue, fallback ATA classique")
                self._incoming_line_seized = False
                self._incoming_seize_ok = False
                return await self.answer_call(fast_voice_seize=False)
            return (True, caller_id, caller_name)
        except Exception as e:
            self._incoming_line_seized = False
            self._incoming_seize_ok = False
            logger.error("Erreur decrochage rapide: {}", e)
            return (False, caller_id, caller_name)
    

    async def join_line_for_listen(self) -> bool:
        """
        Greffe silencieuse sur une ligne deja prise (fixe parallele).

        Contrairement a ``answer_call``, on tente encore ``AT+VLS=1`` apres
        echec ATH1 pour ecouter / enregistrer sans jamais jouer de VTX.

        @returns True si le modem est en mode voix off-hook.
        """
        if not self.supports_voice_serial:
            logger.warning("join_line_for_listen: voix serie indisponible")
            return False
        try:
            response = await self.send_command_full("ATH1", timeout=5.0)
            raw = response.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ")
            logger.info("join_line_for_listen ATH1 -> {}", raw or "(vide)")
            ath_ok = b"OK" in response

            if not ath_ok:
                r_cls = await self.send_command_full(_VOICE_MODE, timeout=3.0)
                logger.info(
                    "join_line_for_listen FCLASS=8 -> {}",
                    r_cls.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ")
                    or "(vide)",
                )
                r_vls = await self.send_command_full(_TAD_OFF_HOOK, timeout=3.0)
                raw_vls = r_vls.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ")
                logger.info("join_line_for_listen VLS=1 -> {}", raw_vls or "(vide)")
                if b"OK" not in r_vls:
                    logger.warning("join_line_for_listen: greffe echouee")
                    return False
            else:
                r_cls = await self.send_command_full(_VOICE_MODE, timeout=3.0)
                if b"OK" in r_cls:
                    await self.send_command_full(_TAD_OFF_HOOK, timeout=3.0)

            await self.prepare_voice_line_after_seize()
            self._incoming_line_seized = True
            self._incoming_seize_ok = True
            self._voice_line_ready = True
            logger.info("join_line_for_listen: modem en ecoute silencieuse")
            return True
        except Exception as exc:
            logger.exception("join_line_for_listen: {}", exc)
            return False

    async def hangup(self) -> bool:
        """
        Raccroche l'appel. Sort d'abord du mode voix transparent si besoin, sinon ATH
        lit du PCM et rate. Timeout court + reset port si blocage.
        """
        self.log_voice_session("hangup_debut")
        self._voice_abort = True
        loop = asyncio.get_event_loop()
        acquired = False
        try:
            try:
                await asyncio.wait_for(self._serial_io_lock.acquire(), timeout=2.0)
                acquired = True
            except asyncio.TimeoutError:
                logger.warning("[MODEM] hangup: verrou serie occupe — reset port")
                await self.run_modem_sync(self._force_serial_reset_sync, timeout=1.0)
                self.log_voice_session("hangup_fin", ok=0, lock_timeout=1)
                return False
            try:
                ok = await self.run_modem_sync(self._force_hangup_sync, timeout=4.0)
                self.log_voice_session("hangup_fin", ok=int(bool(ok)))
                return bool(ok)
            except asyncio.TimeoutError:
                logger.warning("[MODEM] hangup sync timeout — reset port")
                self.log_voice_session("hangup_fin", ok=0, sync_timeout=1)
                return False
            finally:
                if acquired:
                    self._serial_io_lock.release()
        except (OSError, serial.SerialException, RuntimeError) as e:
            if getattr(e, "errno", None) == errno.EIO or isinstance(e, serial.SerialException):
                logger.warning("EIO au raccrochage, reconnexion puis nouvel essai ATH")
                try:
                    await self.run_modem_sync(self._force_serial_reset_sync, timeout=1.0)
                except Exception:
                    pass
                if await self.reconnect():
                    self.log_voice_session("hangup_fin", ok=0, reconnected=1)
                    return False
            logger.error("Erreur lors du raccrochage: {}", e)
            return False
        except Exception as e:
            logger.error("Erreur lors du raccrochage: {}", e)
            return False

    def _force_hangup_sync(self) -> bool:
        """
        Sort de VTX/VRX puis envoie ATH (avec drain et 2e essai si reponse binaire).

        @returns True si OK vu dans la reponse.
        """
        self._voice_abort = True
        self.log_voice_session("force_ath_debut")
        with self._serial_sync_lock:
            if not self.serial_connection or not self.serial_connection.is_open:
                return False
            try:
                if self._vtx_active:
                    try:
                        end_seq = _DTE_END_VOICE_TX_CONEXANT if self._is_conexant else _DTE_END_VOICE_TX
                        self.serial_connection.write(end_seq)
                        self.serial_connection.flush()
                        time.sleep(0.08)
                    except (OSError, serial.SerialException):
                        pass
                    self._vtx_active = False
                self._vrx_transparent_close_sync()
                try:
                    if self._vrx_saved_timeout is not None:
                        self.serial_connection.timeout = self._vrx_saved_timeout
                except (OSError, serial.SerialException):
                    pass
                self._vrx_saved_timeout = None
                self._flush_serial_rx_sync(max_sec=0.55)
                time.sleep(0.1)

                def _ath_once() -> bytes:
                    self.serial_connection.write(b"ATH\r\n")
                    self.serial_connection.flush()
                    deadline = time.monotonic() + 2.0
                    buf = b""
                    max_buf = 1536
                    while time.monotonic() < deadline:
                        if self.serial_connection.in_waiting > 0:
                            buf += self.serial_connection.read(
                                min(512, self.serial_connection.in_waiting)
                            )
                            if b"OK" in buf or b"ERROR" in buf:
                                break
                            if len(buf) >= max_buf:
                                break
                        time.sleep(0.05)
                    return buf

                resp = _ath_once()
                if b"OK" in resp:
                    try:
                        self._send_command_sync("AT+FCLASS=0")
                        self._send_command_sync("AT+VCID=1")
                    except Exception:
                        pass
                    self._reset_voice_session_flags()
                    self.log_voice_session("force_ath_ok", essai=1)
                    return True
                logger.warning(
                    "ATH reponse suspecte ({} o), abandon rapide",
                    len(resp),
                )
                try:
                    self._send_command_sync("AT+FCLASS=0", timeout=1.0)
                    self._send_command_sync("AT+VCID=1", timeout=1.0)
                except Exception:
                    pass
                self._reset_voice_session_flags()
                self.log_voice_session("force_ath_fin", ok=0, essai=1, resp_len=len(resp))
                return False
            except Exception as e:
                logger.warning("[MODEM] force_hangup: {}", e)
                try:
                    self._send_command_sync("AT+FCLASS=0")
                    self._send_command_sync("AT+VCID=1")
                except Exception:
                    pass
                self._reset_voice_session_flags()
                return False

    def _abort_voice_session_sync(self) -> None:
        """
        Coupe VTX/VRX transparent avant ATH (raccrochage UI / release).

        Evite de laisser le modem en flux PCM binaire qui bloque les commandes AT.
        """
        self._voice_abort = True
        self._playback_interrupted = True
        if not self.serial_connection or not self.serial_connection.is_open:
            return
        try:
            if self._vtx_active:
                end_seq = _DTE_END_VOICE_TX_CONEXANT if self._is_conexant else _DTE_END_VOICE_TX
                self.serial_connection.write(end_seq)
                self.serial_connection.flush()
                time.sleep(0.06)
                self._vtx_active = False
            self._vrx_transparent_close_sync()
            self._flush_serial_rx_sync(max_sec=0.25)
        except (OSError, serial.SerialException) as exc:
            logger.warning("_abort_voice_session_sync: {}", exc)

    def _reset_voice_session_flags(self) -> None:
        """Remet a zero les flags voix entre deux appels."""
        self._voice_abort = False
        self._playback_interrupted = False
        self._voice_line_ready = False
        self._vtx_ignore_interrupt_until = 0.0
        # Ne pas garder un "silence" du tour / appel precedent
        # (sinon caller_line_finished() coupe la conversation au demarrage).
        self.last_vrx_stop_reason = None
        self.last_vrx_heard_speech = False

    def voice_session_diag(self) -> dict[str, Any]:
        """
        Etat voix modem pour logs [MODEM] / [APPEL].

        @returns Dictionnaire serialisable (entiers / chaines courtes).
        """
        return {
            "vtx": int(self._vtx_active),
            "seize": int(self._incoming_line_seized),
            "seize_ok": int(self._incoming_seize_ok),
            "line_ready": int(self._voice_line_ready),
            "greeting_played": int(self._greeting_played_on_seize),
            "abort": int(self._voice_abort),
            "outgoing": int(self._outgoing_owns_serial),
            "early_pending": int(self._early_greeting_pending),
            "vrx_reason": self.last_vrx_stop_reason or "-",
        }

    def log_voice_session(self, tag: str, *, level: str = "info", **extra: Any) -> None:
        """
        Journalise l'etat voix courant (grep [MODEM]).

        @param tag Etiquette courte (ex. hangup_debut, VTX_fin).
        @param level Niveau loguru (info, warning, ...).
        @param extra Paires cle=valeur supplementaires.
        """
        diag = self.voice_session_diag()
        parts = [
            f"tag={tag}",
            f"vtx={diag['vtx']}",
            f"seize={diag['seize']}/{diag['seize_ok']}",
            f"line={diag['line_ready']}",
            f"abort={diag['abort']}",
            f"vrx_stop={diag['vrx_reason']}",
        ]
        for key, value in extra.items():
            parts.append(f"{key}={value}")
        getattr(logger, level)("[MODEM] {}", " ".join(parts))

    @staticmethod
    def _normalize_phone_for_command(phone_number: str) -> str:
        """
        Chiffres seuls pour ATD, avec conversion courante +33 / 0033 -> national francais (0...).
        """
        s = (phone_number or "").strip()
        if not s:
            return ""
        digits = "".join(c for c in s if c.isdigit())
        if not digits:
            return ""
        if digits.startswith("0033") and len(digits) > 4:
            return "0" + digits[4:]
        if digits.startswith("33") and len(digits) >= 11:
            return "0" + digits[2:]
        return digits

    async def dial_number(self, phone_number: str, timeout: float = 25.0) -> tuple[bool, str]:
        """
        Compose un numero sortant via ATD et attend un etat modem.

        @param phone_number Numero a composer.
        @param timeout Delai max d'attente de reponse modem.
        @returns Tuple (succes, reponse_brute).
        """
        normalized = self._normalize_phone_for_command(phone_number)
        if not normalized:
            return (False, "numero vide")
        command = f"ATD{normalized};"
        response = await self.send_command_full(command, timeout=timeout, stop_on_ring=False)
        raw = response.decode("utf-8", errors="ignore").strip()
        success = b"CONNECT" in response or b"OK" in response
        return (success, raw)

    async def send_dtmf(self, digit: str) -> bool:
        """
        Envoie une tonalite DTMF pendant un appel via AT+VTS.

        @param digit Touche a envoyer (0-9, *, #, A-D).
        @returns True si le modem confirme l'envoi.
        """
        if not digit:
            return False
        clean = str(digit).strip().upper()
        allowed = set("0123456789*#ABCD")
        if clean not in allowed:
            return False
        # Selon le firmware modem, le format peut varier.
        # On essaie plusieurs syntaxes pour maximiser la compatibilite.
        commands = [
            f'AT+VTS="{clean}"',
            f"AT+VTS={clean}",
            f"AT+VTS={clean},100",
        ]

        async with self._serial_io_lock:
            vrx_was_active = bool(self._vrx_saved_timeout is not None)
            if vrx_was_active:
                # Evite que la reponse AT soit polluee par le flux audio binaire VRX.
                self._vrx_transparent_close_sync()
                await asyncio.sleep(0.08)
            try:
                for command in commands:
                    try:
                        response = await self._send_command_full_unlocked(
                            command, timeout=3.0, stop_on_ring=False
                        )
                        if b"OK" in response:
                            return True
                        logger.debug(
                            "DTMF non confirme pour {} -> {}",
                            command,
                            response.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ") or "(vide)",
                        )
                    except Exception as e:
                        logger.debug("DTMF erreur sur {}: {}", command, e)
                return False
            finally:
                if vrx_was_active:
                    if not self._send_command_sync(_VOICE_RX, expect="CONNECT", timeout=10.0):
                        logger.warning("send_dtmf: reprise VRX echouee apres AT+VTS")

    async def wait_for_dtmf_digit(self, expected: str, timeout_sec: float = 8.0) -> bool:
        """
        Attend qu'une touche DTMF precise soit recue sur la ligne.

        Active AT+VTD=1 (detection DTMF en mode voix) puis ecoute les URC modem
        via ``_process_modem_line``.

        @param expected Touche attendue (0-9, *, #, A-D).
        @param timeout_sec Delai max d'attente.
        @returns True si la bonne touche a ete recue avant timeout.
        """
        expected_norm = str(expected or "1").strip().upper()[:1]
        allowed = set("0123456789*#ABCD")
        if expected_norm not in allowed:
            expected_norm = "1"

        for cmd in ("AT+VTD=1", "AT+VTDD=1"):
            try:
                await self.send_command(cmd, timeout=2.0)
            except Exception as exc:
                logger.debug("Activation DTMF {}: {}", cmd, exc)

        self._dtmf_wait_expected = expected_norm
        self._dtmf_last_digit = None
        self._dtmf_event = asyncio.Event()
        try:
            await asyncio.wait_for(self._dtmf_event.wait(), timeout=float(timeout_sec))
            got = (self._dtmf_last_digit or "").upper()
            ok = got == expected_norm
            if not ok:
                logger.info("DTMF recu {} != attendu {}", got, expected_norm)
            return ok
        except asyncio.TimeoutError:
            logger.info("DTMF timeout apres {}s (attendu {})", timeout_sec, expected_norm)
            return False
        finally:
            self._dtmf_wait_expected = None
            self._dtmf_event = None
            self._dtmf_last_digit = None

    def _send_command_sync(self, command: str, expect: str = "OK", timeout: float = 5.0) -> bool:
        """Envoie une commande AT et attend la réponse (synchrone, pour usage dans executor)."""
        if not self.serial_connection or not self.serial_connection.is_open:
            return False
        try:
            self.serial_connection.write(f"{command}\r\n".encode())
            self.serial_connection.flush()
            deadline = time.monotonic() + timeout
            buf = b""
            while time.monotonic() < deadline:
                if self.serial_connection.in_waiting > 0:
                    buf += self.serial_connection.read(self.serial_connection.in_waiting)
                    if expect.encode() in buf or b"ERROR" in buf:
                        break
                time.sleep(0.05)
            ok = expect.encode() in buf
            if not ok:
                logger.debug("_send_command_sync {} -> {}", command, buf.decode("utf-8", errors="ignore"))
            return ok
        except Exception as e:
            logger.debug("_send_command_sync {}: {}", command, e)
            return False

    def _play_wav_serial_impl(self, wav_path: Path, already_in_voice_mode: bool = False) -> bool:
        """
        Joue un WAV vers la ligne via le mode voix (port série).
        WAV converti au profil actif (USR 16-bit / 11 kHz ou Conexant 8-bit / 8 kHz).
        Si already_in_voice_mode=True (ex. apres answer_call en mode voix), on ne renvoie pas
        FCLASS=8 ni VLS=1 pour eviter de faire raccrocher le modem.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            logger.warning("play_wav_serial: modem non connecte")
            return False
        try:
            try:
                pcm = wav_path_to_modem_pcm(
                    wav_path,
                    profile=self.voice_profile,
                    normalize=not wav_matches_modem_profile(wav_path, profile=self.voice_profile),
                )
            except Exception as conv_exc:
                logger.warning("Conversion WAV modem echouee ({}), lecture brute", conv_exc)
                pcm = b""
                with wave.open(str(wav_path), "rb") as wf:
                    nch, sampwidth, framerate = wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
                    logger.info("WAV: {} Hz, {} canaux, {} bit", framerate, nch, sampwidth * 8)
                    raw = wf.readframes(wf.getnframes())
                    if sampwidth == self.voice_profile.sample_width and nch == 1:
                        pcm = raw
            if not pcm:
                logger.warning("play_wav_serial: aucun echantillon audio")
                return False
            peak = pcm_chunk_peak(pcm, sample_width=self.voice_profile.sample_width)
            logger.info(
                "play_wav_serial: peak PCM={} width={} (fichier {})",
                peak,
                self.voice_profile.sample_width,
                wav_path.name,
            )
            min_peak = 8 if self.voice_profile.sample_width == 1 else 400
            if peak < min_peak:
                logger.warning("play_wav_serial: niveau tres faible (peak={})", peak)
            voice_ready = bool(already_in_voice_mode and self._voice_line_ready)
            if not already_in_voice_mode:
                if not self._send_command_sync(_VOICE_MODE):
                    logger.warning("play_wav_serial: AT+FCLASS=8 a echoue")
                    return False
            if not voice_ready:
                vsd = _VSD_DISABLE_CONEXANT if self._is_conexant else _VSD_DISABLE_USR
                self._send_command_sync(vsd)
                self._apply_voice_gains_sync()
                if not self._apply_vsm_sync():
                    logger.warning("play_wav_serial: VSM a echoue, on tente quand meme VTX")
                self._voice_line_ready = True
            if not already_in_voice_mode:
                if not self._send_command_sync(_TAD_OFF_HOOK):
                    logger.warning("play_wav_serial: AT+VLS=1 a echoue")
                    return False
            else:
                # Apres VRX (bip / enregistrement) : fermer le flux transparent avant VTX.
                self._vrx_transparent_close_sync()
                self._flush_serial_rx_sync(max_sec=0.3)
            if not self._send_command_sync(_VOICE_TX, expect="CONNECT", timeout=10.0):
                logger.warning("play_wav_serial: AT+VTX (CONNECT) a echoue")
                return False
            self._vtx_active = True
            self._playback_interrupted = False
            self._vtx_event_scanner = _VrxHangupScanner()
            # Court delai pour ignorer un RING residuel, PAS tout l'accueil :
            # sinon un raccrochage pendant l'annonce n'est jamais vu.
            self._vtx_ignore_interrupt_until = time.monotonic() + 0.4
            self._flush_serial_rx_sync()
            logger.info(
                "Lecture WAV vers ligne (VTX), {} octets PCM {} Hz {}-bit",
                len(pcm),
                self.voice_profile.sample_rate,
                self.voice_profile.sample_width * 8,
            )
            if not self._vtx_write_pcm_paced_monotonic_sync(pcm):
                self._playback_interrupted = True
            end_seq = _DTE_END_VOICE_TX_CONEXANT if self._is_conexant else _DTE_END_VOICE_TX
            self.serial_connection.write(end_seq)
            self.serial_connection.flush()
            self._vtx_active = False
            time.sleep(0.08)
            if self._drain_rx_check_hangup_sync():
                self._playback_interrupted = True
            interrupted = bool(self._playback_interrupted)
            self.log_voice_session(
                "VTX_fin",
                fichier=wav_path.name,
                octets=len(pcm),
                interrupted=int(interrupted),
            )
            return not interrupted
        except Exception as e:
            self._vtx_active = False
            logger.exception("Erreur lecture WAV via serie: {}", e)
            return False

    def _serial_carrier_cd_sync(self) -> Optional[bool]:
        """Lit DCD/cd si pyserial l'expose (USB sortant : souvent toujours False)."""
        conn = self.serial_connection
        if conn is None:
            return None
        try:
            return bool(conn.cd)
        except Exception:
            return None

    def _read_vrx_chunk_unlocked(self) -> bytes:
        """
        Lit un bloc du flux VRX sans bloquer longtemps (tolère EIO USB).

        @returns Octets lus sur le port série.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return b""
        try:
            pending = self.serial_connection.in_waiting
        except OSError as e:
            if getattr(e, "errno", None) != errno.EIO:
                raise
            pending = 0
        if pending > 0:
            return self.serial_connection.read(min(pending, 4096))
        old_timeout = self.serial_connection.timeout
        try:
            self.serial_connection.timeout = 0.2
            return self.serial_connection.read(4096) or b""
        except OSError as e:
            if getattr(e, "errno", None) == errno.EIO:
                return b""
            raise
        finally:
            self.serial_connection.timeout = old_timeout

    def _record_wav_serial_impl(
        self,
        duration_sec: float,
        out_path: Path,
        already_in_voice_mode: bool = False,
        stop_on_remote_hangup: bool = False,
        silence_timeout_sec: float = 0.0,
        silence_threshold: int = 14,
    ) -> bool:
        """
        Enregistre l'audio depuis la ligne telephonique via le mode voix (AT+VRX).
        Si already_in_voice_mode=True (ex. apres answer_call + play), on ne renvoie pas
        FCLASS=8 ni VLS=1 pour eviter de faire raccrocher le modem.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            logger.warning("record_wav_serial: modem non connecte")
            self.last_vrx_stop_reason = "port_closed"
            return False
        if not self._is_conexant:
            logger.warning("record_wav_serial: modem non Conexant, VRX non garanti")
        self.last_vrx_stop_reason = None
        self.last_vrx_heard_speech = False
        vrx_opened = False
        try:
            if not already_in_voice_mode:
                if not self._send_command_sync(_VOICE_MODE):
                    logger.warning("record_wav_serial: AT+FCLASS=8 a echoue")
                    return False
            # Detection silence logicielle (pas VSD modem) : VSD agressif a deja
            # provoque des resets USB ACM sur le hub Pi. Les marqueurs DLE suffisent.
            vsd = _VSD_DISABLE_CONEXANT if self._is_conexant else _VSD_DISABLE_USR
            self._send_command_sync(vsd)
            if not self._apply_vsm_sync():
                logger.warning("record_wav_serial: VSM a echoue, on tente quand meme VRX")
            if not already_in_voice_mode:
                if not self._send_command_sync(_TAD_OFF_HOOK):
                    logger.warning("record_wav_serial: AT+VLS=1 a echoue")
                    return False
            if not self._send_command_sync(_VOICE_RX, expect="CONNECT", timeout=10.0):
                logger.warning("record_wav_serial: AT+VRX (CONNECT) a echoue")
                self.last_vrx_stop_reason = "vrx_error"
                return False
            vrx_opened = True
            if stop_on_remote_hangup or silence_timeout_sec > 0:
                details = []
                if stop_on_remote_hangup:
                    details.append("raccrochage distant")
                if silence_timeout_sec > 0:
                    details.append(f"silence {silence_timeout_sec:.0f}s")
                logger.info(
                    "Enregistrement ligne (VRX) max {} s — arret anticipe si {}",
                    duration_sec,
                    " ou ".join(details),
                )
            else:
                logger.info("Enregistrement ligne (VRX) pendant {} s...", duration_sec)
            chunks = []
            deadline = time.monotonic() + duration_sec
            carrier_initial = self._serial_carrier_cd_sync() if stop_on_remote_hangup else None
            effective_silence_threshold = self.voice_profile.silence_threshold_from_u8(
                max(8, int(silence_threshold))
            )
            hangup_scanner = _VrxHangupScanner()
            tone_threshold = max(
                effective_silence_threshold * 2,
                28 if self.voice_profile.sample_width <= 1 else 5000,
            )
            disconnect_scanner = _VrxDisconnectToneScanner(
                threshold=tone_threshold,
                sample_rate=self.voice_profile.sample_rate,
                min_beeps=3,
            )
            silence_started: Optional[float] = None
            heard_speech = False
            min_record_before_silence = 0.8
            no_speech_hangup_sec = max(6.0, float(silence_timeout_sec) + 2.0)
            min_record_before_hangup = _VRX_MIN_HANGUP_GRACE_SEC
            record_started = time.monotonic()
            old_timeout = self.serial_connection.timeout
            self.serial_connection.timeout = 0.2
            io_error = False
            try:
                while time.monotonic() < deadline:
                    if self._voice_abort:
                        logger.info("Enregistrement VRX interrompu (voice_abort)")
                        self.last_vrx_stop_reason = "voice_abort"
                        break
                    if not self.serial_connection or not self.serial_connection.is_open:
                        logger.warning("Enregistrement VRX interrompu: port serie ferme")
                        break
                    try:
                        elapsed_record = time.monotonic() - record_started
                        if stop_on_remote_hangup and elapsed_record >= min_record_before_hangup:
                            carrier_now = self._serial_carrier_cd_sync()
                            if carrier_initial is True and carrier_now is False:
                                logger.info(
                                    "Enregistrement VRX interrompu: perte porteuse DCD (raccrochage probable)"
                                )
                                self.last_vrx_stop_reason = "hangup_dcd"
                                break
                        raw = self._read_vrx_chunk_unlocked()
                        if raw:
                            chunks.append(raw)
                            tones = disconnect_scanner.feed(
                                raw, sample_width=self.voice_profile.sample_width
                            )
                            if stop_on_remote_hangup and tones:
                                logger.info(
                                    "Enregistrement VRX interrompu: tonalite operateur (bips fin)"
                                )
                                self.last_vrx_stop_reason = "disconnect_tones"
                                break
                            if stop_on_remote_hangup and elapsed_record >= min_record_before_hangup:
                                if hangup_scanner.feed(raw):
                                    logger.info(
                                        "Enregistrement VRX interrompu: marqueur fin de ligne dans le flux serie"
                                    )
                                    self.last_vrx_stop_reason = "hangup_marker"
                                    break
                            if disconnect_scanner.heard_speech:
                                heard_speech = True
                            if silence_timeout_sec > 0:
                                elapsed = time.monotonic() - record_started
                                peak = pcm_chunk_peak(
                                    raw, sample_width=self.voice_profile.sample_width
                                )
                                if peak >= effective_silence_threshold:
                                    if heard_speech and not disconnect_scanner.in_beep_train:
                                        silence_started = None
                                elif heard_speech:
                                    if elapsed >= min_record_before_silence:
                                        if silence_started is None:
                                            silence_started = time.monotonic()
                                        elif time.monotonic() - silence_started >= silence_timeout_sec:
                                            logger.info(
                                                "Enregistrement VRX interrompu: silence {} s apres la parole",
                                                silence_timeout_sec,
                                            )
                                            self.last_vrx_stop_reason = "silence"
                                            break
                                elif elapsed >= no_speech_hangup_sec:
                                    logger.info(
                                        "Enregistrement VRX interrompu: aucun message apres {} s",
                                        no_speech_hangup_sec,
                                    )
                                    self.last_vrx_stop_reason = "silence"
                                    break
                        else:
                            time.sleep(0.02)
                    except (OSError, serial.SerialException) as e:
                        logger.warning("Enregistrement VRX I/O erreur (modem deconnecte?): {}", e)
                        io_error = True
                        self.last_vrx_stop_reason = "io_error"
                        break
                if not io_error and self.serial_connection and self.serial_connection.is_open:
                    try:
                        end_rx = _DTE_END_VOICE_RX_CONEXANT if self._is_conexant else _DTE_END_VOICE_TX
                        self.serial_connection.write(end_rx)
                        self.serial_connection.flush()
                        time.sleep(0.1)
                        leftover = bytearray()
                        while self.serial_connection.in_waiting > 0:
                            leftover.extend(self.serial_connection.read(self.serial_connection.in_waiting))
                        # Ne pas recoller les bips / NO CARRIER dans le message.
                        if leftover and self.last_vrx_stop_reason not in (
                            "disconnect_tones",
                            "hangup_marker",
                            "hangup_dcd",
                        ):
                            chunks.append(bytes(leftover))
                    except (OSError, serial.SerialException):
                        pass
            finally:
                try:
                    if self.serial_connection and self.serial_connection.is_open:
                        self.serial_connection.timeout = old_timeout
                except (OSError, serial.SerialException):
                    pass
            if self.last_vrx_stop_reason is None and time.monotonic() >= deadline:
                self.last_vrx_stop_reason = "timeout"
            data = b"".join(chunks)
            heard_speech = bool(heard_speech or disconnect_scanner.heard_speech)
            tone_trim = float(getattr(disconnect_scanner, "trim_sec", 0.0) or 0.0)
            if self.last_vrx_stop_reason == "disconnect_tones":
                pass
            else:
                # Filet : bips encore dans la queue alors qu'on a coupe sur silence.
                tone_trim = _scan_hangup_tone_trim(
                    data,
                    sample_width=self.voice_profile.sample_width,
                    sample_rate=self.voice_profile.sample_rate,
                    threshold=tone_threshold,
                )
                if tone_trim > 0:
                    logger.info(
                        "Tonalite operateur detectee en post-traitement ({:.1f} s a couper)",
                        tone_trim,
                    )
                    self.last_vrx_stop_reason = self.last_vrx_stop_reason or "disconnect_tones"
            if tone_trim > 0:
                before = len(data)
                data = _trim_pcm_tail(
                    data,
                    sample_width=self.voice_profile.sample_width,
                    sample_rate=self.voice_profile.sample_rate,
                    trim_sec=tone_trim,
                )
                if len(data) < before:
                    logger.info(
                        "Message coupe: {} ms de bips operateur retires",
                        int(1000 * (before - len(data)) / max(1, self.voice_profile.bytes_per_sec)),
                    )
                remain_sec = len(data) / float(max(1, self.voice_profile.bytes_per_sec))
                if not heard_speech or remain_sec < 0.4:
                    heard_speech = False
                    logger.info("Raccrochage sans message (bips seulement, rien a garder)")
                    self.last_vrx_heard_speech = False
                    self.log_voice_session(
                        "VRX_fin",
                        fichier=out_path.name,
                        octets=0,
                        raison="disconnect_tones_empty",
                    )
                    self._flush_serial_rx_sync(max_sec=0.25)
                    vrx_opened = False
                    return True
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(out_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(self.voice_profile.sample_width)
                wf.setframerate(self.voice_profile.sample_rate)
                wf.writeframes(data)
            elapsed = time.monotonic() - record_started
            self.last_vrx_heard_speech = bool(heard_speech)
            self.log_voice_session(
                "VRX_fin",
                fichier=out_path.name,
                octets=len(data),
                duree_s=f"{elapsed:.1f}",
                raison=self.last_vrx_stop_reason or "ok",
            )
            logger.info("Enregistrement VRX sauve: {} ({} octets)", out_path.name, len(data))
            self._flush_serial_rx_sync(max_sec=0.25)
            vrx_opened = False
            return True
        except Exception as e:
            logger.exception("Erreur enregistrement VRX via serie: {}", e)
            return False
        finally:
            if vrx_opened:
                try:
                    self._vrx_transparent_close_sync()
                except Exception:
                    pass

    def _vrx_transparent_close_sync(self) -> None:
        """Sort du flux transparent AT+VRX (donnees PCM) sans quitter le mode voix."""
        if not self.serial_connection or not self.serial_connection.is_open:
            return
        try:
            end_rx = _DTE_END_VOICE_RX_CONEXANT if self._is_conexant else _DTE_END_VOICE_TX
            self.serial_connection.write(end_rx)
            self.serial_connection.flush()
            time.sleep(0.1)
            while self.serial_connection.in_waiting > 0:
                self.serial_connection.read(self.serial_connection.in_waiting)
        except (OSError, serial.SerialException):
            pass

    def _vrx_stream_open_sync(self, already_in_voice_mode: bool) -> bool:
        """Passe en mode voix et ouvre AT+VRX (flux PCM du profil actif)."""
        if not self.serial_connection or not self.serial_connection.is_open:
            logger.warning("vrx_stream_open: modem non connecte")
            return False
        try:
            if not already_in_voice_mode:
                if not self._send_command_sync(_VOICE_MODE):
                    logger.warning("vrx_stream_open: AT+FCLASS=8 a echoue")
                    return False
            vsd = _VSD_DISABLE_CONEXANT if self._is_conexant else _VSD_DISABLE_USR
            self._send_command_sync(vsd)
            self._apply_vsm_sync()
            if not already_in_voice_mode:
                if not self._send_command_sync(_TAD_OFF_HOOK):
                    logger.warning("vrx_stream_open: AT+VLS=1 a echoue")
                    return False
            if not self._send_command_sync(_VOICE_RX, expect="CONNECT", timeout=10.0):
                logger.warning("vrx_stream_open: AT+VRX (CONNECT) a echoue")
                return False
            self._vrx_saved_timeout = self.serial_connection.timeout
            self.serial_connection.timeout = 0.25
            return True
        except Exception as e:
            logger.exception("vrx_stream_open: {}", e)
            return False

    def _vrx_stream_finalize_sync(self) -> None:
        """Ferme VTX si ouvert, puis le flux VRX transparent, et restaure le timeout serie."""
        if self._vtx_active and self.serial_connection and self.serial_connection.is_open:
            try:
                end_seq = _DTE_END_VOICE_TX_CONEXANT if self._is_conexant else _DTE_END_VOICE_TX
                self.serial_connection.write(end_seq)
                self.serial_connection.flush()
                time.sleep(0.05)
            except (OSError, serial.SerialException):
                pass
            self._vtx_active = False
        self._vrx_transparent_close_sync()
        try:
            if self.serial_connection and self.serial_connection.is_open and self._vrx_saved_timeout is not None:
                self.serial_connection.timeout = self._vrx_saved_timeout
        except (OSError, serial.SerialException):
            pass
        self._vrx_saved_timeout = None

    def _apply_voice_pcm_params_sync(self) -> None:
        """Configure VSD / VSM / gains pour le PCM du profil actif (avant VTX ou VRX)."""
        vsd = _VSD_DISABLE_CONEXANT if self._is_conexant else _VSD_DISABLE_USR
        self._send_command_sync(vsd)
        self._apply_voice_gains_sync()
        self._apply_vsm_sync()

    def _vtx_begin_sync(self) -> bool:
        """
        Ferme le flux VRX et ouvre AT+VTX pour un talkspurt micro continu.

        @returns True si CONNECT VTX OK.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return False
        try:
            self._vrx_transparent_close_sync()
            self._flush_serial_rx_sync(max_sec=0.25)
            self._apply_voice_pcm_params_sync()
            if not self._send_command_sync(_VOICE_TX, expect="CONNECT", timeout=10.0):
                logger.warning("vtx_begin: AT+VTX CONNECT a echoue")
                self._vtx_active = False
                return False
            self._vtx_active = True
            return True
        except Exception as e:
            logger.warning("vtx_begin: {}", e)
            self._vtx_active = False
            return False

    def _vtx_write_paced_sync(self, u8_pcm: bytes) -> bool:
        """
        Envoie du PCM 8-bit 8 kHz pendant un VTX ouvert, au rythme temps reel.

        @param u8_pcm Octets PCM unsigned 8-bit mono 8 kHz.
        @returns True si ecriture OK (False si abort ou erreur).
        """
        return self._vtx_write_pcm_paced_monotonic_sync(u8_pcm)

    def _vtx_write_pcm_paced_monotonic_sync(self, u8_pcm: bytes) -> bool:
        """
        Envoie du PCM 8 kHz 8-bit avec horloge monotone (evite saccades / underrun).

        @param u8_pcm Octets PCM unsigned 8-bit mono 8 kHz.
        @returns True si ecriture OK.
        """
        if not u8_pcm:
            return True
        if not self._vtx_active or not self.serial_connection or not self.serial_connection.is_open:
            return False
        try:
            chunk = self.voice_profile.vtx_chunk_bytes
            rate = float(self.voice_profile.bytes_per_sec)
            next_deadline = time.monotonic()
            for offset in range(0, len(u8_pcm), chunk):
                if self._voice_abort:
                    return False
                if self._peek_serial_interrupt_sync():
                    self._playback_interrupted = True
                    return False
                piece = u8_pcm[offset : offset + chunk]
                self.serial_connection.write(_escape_dle_pcm(piece))
                next_deadline += len(piece) / rate
                wait = next_deadline - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                elif wait < -0.12:
                    next_deadline = time.monotonic()
            return True
        except Exception as e:
            logger.warning("vtx_write: {}", e)
            return False

    def _vtx_end_reopen_vrx_sync(self) -> bool:
        """
        Termine VTX (DLE ETX) puis rouvre AT+VRX pour reprendre l'ecoute ligne.

        @returns True si reprise VRX OK.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            self._vtx_active = False
            return False
        try:
            if self._vtx_active:
                end_seq = _DTE_END_VOICE_TX_CONEXANT if self._is_conexant else _DTE_END_VOICE_TX
                self.serial_connection.write(end_seq)
                self.serial_connection.flush()
                time.sleep(0.08)
            self._vtx_active = False
            if not self._send_command_sync(_VOICE_RX, expect="CONNECT", timeout=10.0):
                logger.warning("vtx_end: reprise AT+VRX a echoue")
                return False
            # Reprend le mode lecture non bloquante utilise par le stream sortant.
            self.serial_connection.timeout = 0.25
            if self._vrx_saved_timeout is None:
                self._vrx_saved_timeout = 0.25
            return True
        except Exception as e:
            logger.warning("vtx_end: {}", e)
            self._vtx_active = False
            return False

    def _half_duplex_uplink_sync(self, u8_pcm: bytes) -> bool:
        """
        Compat : une rafale VTX puis reprise VRX (preferer begin/write/end talkspurt).

        @param u8_pcm PCM 8-bit 8 kHz a envoyer.
        @returns True si envoi et reprise VRX OK.
        """
        if not u8_pcm or not self.serial_connection or not self.serial_connection.is_open:
            return True
        try:
            if not self._vtx_begin_sync():
                return False
            if not self._vtx_write_paced_sync(u8_pcm):
                self._vtx_end_reopen_vrx_sync()
                return False
            return self._vtx_end_reopen_vrx_sync()
        except Exception as e:
            logger.warning("half_duplex_uplink: {}", e)
            self._vtx_active = False
            return False

    @property
    def supports_voice_serial(self) -> bool:
        """True si le modem est pret pour le mode voix serie (USR 5637 / Conexant, etc.)."""
        return bool(self.is_initialized)

    def remote_hangup_detected(self) -> bool:
        """
        True si le dernier enregistrement VRX s'est arrete pour raccrochage distant.

        @returns True apres marqueur DLE / perte DCD / bips operateur / erreur I/O pendant VRX.
        """
        return self.last_vrx_stop_reason in (
            "hangup_marker",
            "hangup_dcd",
            "port_closed",
            "io_error",
            "disconnect_tones",
        )

    def caller_line_finished(self) -> bool:
        """
        True si l'appelant a probablement quitte la ligne.

        Le motif ``silence`` n'est PAS un raccrochage : c'est la fin d'un tour
        d'ecoute. L'inclure faisait sauter le mode conversation au tour suivant.

        @returns True pour hangup distant / perte port / bips operateur.
        """
        return self.last_vrx_stop_reason in (
            "hangup_marker",
            "hangup_dcd",
            "port_closed",
            "io_error",
            "disconnect_tones",
        )

    async def play_wav_via_serial(
        self, wav_path: Path, already_in_voice_mode: bool = False
    ) -> bool:
        """
        Joue un fichier WAV vers la ligne téléphonique via le port série (mode voix).
        À utiliser après answer_call(). Passer already_in_voice_mode=True si on vient de décrocher
        en mode voix (FCLASS=8, VLS=1) pour ne pas renvoyer ces commandes et éviter de couper l'appel.
        """
        loop = asyncio.get_event_loop()
        async with self._serial_io_lock:
            return await self.run_modem_sync(
                self._play_wav_serial_impl,
                wav_path,
                already_in_voice_mode,
                timeout=120.0,
            )

    async def record_wav_via_serial(
        self,
        duration_sec: float,
        out_path: Path,
        already_in_voice_mode: bool = False,
        *,
        stop_on_remote_hangup: bool = False,
        silence_timeout_sec: float = 0.0,
    ) -> bool:
        """
        Enregistre l'audio depuis la ligne téléphonique via le port série (AT+VRX).
        Passer already_in_voice_mode=True si on vient de answer_call + play pour ne pas recouper l'appel.

        Si ``stop_on_remote_hangup`` est True, coupe l'enregistrement dès détection d'un marqueur type
        NO CARRIER dans le flux ou d'une perte DCD quand la porteuse était True au départ.
        Si ``silence_timeout_sec`` > 0, coupe après ce délai de silence une fois la parole terminée.
        """
        loop = asyncio.get_event_loop()
        async with self._serial_io_lock:
            return await self.run_modem_sync(
                partial(
                    self._record_wav_serial_impl,
                    duration_sec,
                    out_path,
                    already_in_voice_mode,
                    stop_on_remote_hangup,
                    silence_timeout_sec,
                ),
                timeout=max(15.0, float(duration_sec) + 12.0),
            )

    async def start_outgoing_vrx_stream(self, already_in_voice_mode: bool = False) -> bool:
        """Ouvre le flux VRX pour une session sortante (streaming vers WebSocket)."""
        async with self._serial_io_lock:
            return await self.run_modem_sync(
                self._vrx_stream_open_sync,
                already_in_voice_mode,
                timeout=12.0,
            )

    async def end_outgoing_vrx_stream(self) -> None:
        """Ferme le flux VRX (avant ATH)."""
        async with self._serial_io_lock:
            await self.run_modem_sync(self._vrx_stream_finalize_sync, timeout=5.0)

    async def read_outgoing_vrx_chunk(self, nbytes: int = 2048) -> bytes:
        """Lit des octets PCM 8-bit depuis le flux VRX (lock court)."""
        async with self._serial_io_lock:
            return await self.run_modem_sync(self._serial_read_fixed, nbytes, timeout=2.0)

    def _serial_read_fixed(self, nbytes: int) -> bytes:
        if not self.serial_connection or not self.serial_connection.is_open:
            return b""
        try:
            return self.serial_connection.read(nbytes)
        except (OSError, serial.SerialException):
            return b""

    async def half_duplex_send_uplink_u8(self, u8_pcm: bytes) -> bool:
        """Envoie une rafale micro vers la ligne (VTX) puis reprend VRX."""
        if not u8_pcm:
            return True
        async with self._serial_io_lock:
            return await self.run_modem_sync(self._half_duplex_uplink_sync, u8_pcm, timeout=8.0)

    async def begin_outgoing_vtx(self) -> bool:
        """
        Ouvre un talkspurt micro (ferme VRX, AT+VTX).

        @returns True si VTX pret.
        """
        async with self._serial_io_lock:
            return await self.run_modem_sync(self._vtx_begin_sync, timeout=8.0)

    async def write_outgoing_vtx_u8(self, u8_pcm: bytes) -> bool:
        """
        Ecrit du PCM pendant un talkspurt VTX deja ouvert.

        @param u8_pcm PCM 8-bit 8 kHz.
        @returns True si ecriture OK.
        """
        if not u8_pcm:
            return True
        async with self._serial_io_lock:
            return await self.run_modem_sync(self._vtx_write_paced_sync, u8_pcm, timeout=8.0)

    async def end_outgoing_vtx_reopen_vrx(self) -> bool:
        """
        Ferme le talkspurt VTX et rouvre VRX.

        @returns True si VRX repris.
        """
        async with self._serial_io_lock:
            return await self.run_modem_sync(self._vtx_end_reopen_vrx_sync, timeout=8.0)

    @staticmethod
    def _is_serial_io_fault(exc: BaseException) -> bool:
        """
        True si l'erreur indique un port USB ACM mort / a reouvrir.

        pyserial remonte souvent ``SerialException("Could not configure port: (5, ...)")``
        sans ``errno`` renseigne - il faut matcher le message.

        @param exc Exception capturée.
        @returns True pour declencher une reconnexion.
        """
        err_no = getattr(exc, "errno", None)
        if err_no in (errno.EIO, errno.ENODEV, errno.ENOENT):
            return True
        msg = str(exc).lower()
        return (
            "input/output error" in msg
            or "could not configure port" in msg
            or "device disconnected" in msg
            or "device reports readiness" in msg
        )

    def _read_serial_unsolicited_unlocked(self) -> bytes:
        """
        Lit les messages spontanes du modem (RING, NMBR=, etc.) sans bloquer longtemps.

        Evite ``in_waiting`` seul : sur certains USB ACM (USR5637), un EIO sur ``in_waiting``
        empechait toute detection d'appel entrant pendant des jours.

        @returns Octets lus sur le port serie (peut etre vide).
        @raises OSError|serial.SerialException Sur panne port (a reconnecter).
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return b""
        pending = 0
        try:
            pending = self.serial_connection.in_waiting
        except (OSError, serial.SerialException) as e:
            if self._is_serial_io_fault(e):
                raise
            pending = 0
        if pending > 0:
            return self.serial_connection.read(min(pending, 256)) or b""
        # Timeout court deja pose a l'init / reconnect : ne pas reconfigurer a chaque boucle
        # (set timeout sur ACM mort -> "Could not configure port" en boucle).
        try:
            return self.serial_connection.read(256) or b""
        except (OSError, serial.SerialException) as e:
            if self._is_serial_io_fault(e):
                raise
            return b""

    async def monitor_calls(self):
        """
        Surveille les appels entrants en lisant les données du modem.
        Tolère les EIO (errno 5) fréquents sur certains modems USB sans spammer les logs.
        """
        if not self.serial_connection:
            raise RuntimeError("Modem non initialisé")

        logger.info("Surveillance des appels entrants...")
        buffer = b""
        last_eio_log = 0.0
        eio_count = 0
        eio_since_reconnect = 0

        # Lecture non bloquante pour la boucle de surveillance.
        try:
            async with self._serial_io_lock:
                if self.serial_connection and self.serial_connection.is_open:
                    self.serial_connection.timeout = 0.05
        except (OSError, serial.SerialException) as e:
            logger.warning("Impossible de poser timeout surveillance: {}", e)

        while self.is_initialized:
            try:
                if self._outgoing_owns_serial:
                    await asyncio.sleep(0.15)
                    continue
                if not self.serial_connection or not self.serial_connection.is_open:
                    logger.warning("Port série fermé, tentative de reconnexion...")
                    if await self.reconnect():
                        eio_since_reconnect = 0
                        try:
                            async with self._serial_io_lock:
                                if self.serial_connection and self.serial_connection.is_open:
                                    self.serial_connection.timeout = 0.05
                        except (OSError, serial.SerialException):
                            pass
                        continue
                    await asyncio.sleep(2.0)
                    continue
                data = b""
                async with self._serial_io_lock:
                    if not self.serial_connection or not self.serial_connection.is_open:
                        continue
                    data = self._read_serial_unsolicited_unlocked()
                if data:
                    eio_since_reconnect = 0
                    buffer += data
                    # Un flux VRX orphelin (PCM) n'a pas de CRLF : ne pas tourner en boucle
                    # sur l'event loop sinon /health et le relais WS meurent.
                    if len(buffer) > 4096 and b"\r\n" not in buffer[:4096]:
                        logger.warning(
                            "[MODEM] flux serie sans commande AT ({} o) — purge PCM orphelin",
                            len(buffer),
                        )
                        buffer = b""
                        await asyncio.sleep(0.05)
                        continue
                    while b"\r\n" in buffer:
                        line, buffer = buffer.split(b"\r\n", 1)
                        line = line.strip()
                        if line:
                            # Seize synchrone au RING avant tout callback asyncio
                            # (sinon answer_call arrive ~1s trop tard et le fixe sonne).
                            if self._is_incoming_ring_line(line):
                                async with self._serial_io_lock:
                                    if (
                                        self.instant_ring_seize
                                        and not self._incoming_line_seized
                                        and not self._outgoing_owns_serial
                                    ):
                                        self._try_voice_seize_now("ring")
                                    if (
                                        self._incoming_seize_ok
                                        and self.early_greeting_enabled
                                        and not self._greeting_played_on_seize
                                    ):
                                        self._early_greeting_pending = True
                                        played = await self.run_modem_sync(
                                            self._play_early_greeting_sync,
                                            timeout=45.0,
                                        )
                                        self._greeting_played_on_seize = bool(played)
                                        self._early_greeting_pending = False
                            await self._process_modem_line(line)
                    await asyncio.sleep(0)
                else:
                    await asyncio.sleep(0.05)
            except (OSError, serial.SerialException) as e:
                if not self.is_initialized:
                    break
                if self._is_serial_io_fault(e):
                    eio_count += 1
                    eio_since_reconnect += 1
                    now = time.monotonic()
                    if now - last_eio_log >= 30.0:
                        logger.warning(
                            "Panne port modem ({}) - {} depuis derniere reconnexion",
                            e,
                            eio_since_reconnect,
                        )
                        last_eio_log = now
                    if eio_since_reconnect >= 5:
                        logger.warning(
                            "Reconnexion modem apres panne serie ({} erreurs)",
                            eio_count,
                        )
                        if await self.reconnect():
                            eio_since_reconnect = 0
                            buffer = b""
                            try:
                                async with self._serial_io_lock:
                                    if self.serial_connection and self.serial_connection.is_open:
                                        self.serial_connection.timeout = 0.05
                            except (OSError, serial.SerialException):
                                pass
                        else:
                            await asyncio.sleep(2.0)
                    else:
                        await asyncio.sleep(0.4)
                else:
                    logger.error("Erreur OS sur le modem: {}", e)
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Erreur lors de la surveillance: {}", e)
                await asyncio.sleep(1)
    
    @staticmethod
    def _is_incoming_ring_line(line: bytes) -> bool:
        """
        True si la ligne serie est un RING entrant (pas NMBR= melange).

        @param line Ligne brute modem.
        @returns True pour ``RING`` ou ``RING ...``.
        """
        s = line.decode("utf-8", errors="ignore").strip().upper()
        if not s or s.startswith("NMBR"):
            return False
        return s == "RING" or s.startswith("RING")

    def _voice_seize_vls_only_sync_unlocked(self, *, fast: bool = True) -> bool:
        """
        Decrochage rapide style Call Attendant : FCLASS=8 + VSD + VLS=1 sans ATA.

        Plus rapide et evite souvent le NO CARRIER du 1er ATA sur lignes FR.
        Peut laisser la messagerie operateur gagner si le reseau exige un vrai ATA.

        @param fast Timeouts AT courts.
        @returns True si VLS=1 confirme.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return False
        try:
            old_t = self.serial_connection.timeout
            read_timeout = 0.10 if fast else 0.35
            at_deadline = 0.30 if fast else 0.55
            self.serial_connection.timeout = read_timeout

            def _at(cmd: str, *, extra: float = 0.0) -> bytes:
                self.serial_connection.write(f"{cmd}\r\n".encode())
                self.serial_connection.flush()
                deadline = time.monotonic() + at_deadline + extra
                buf = b""
                while time.monotonic() < deadline:
                    chunk = self.serial_connection.read(128) or b""
                    if chunk:
                        buf += chunk
                        if b"OK" in buf or b"CONNECT" in buf.upper():
                            break
                        upper = buf.upper()
                        if b"NO CARRIER" in upper or b"ERROR" in upper:
                            break
                    else:
                        time.sleep(0.01)
                return buf

            r1 = _at(_VOICE_MODE)
            if b"OK" not in r1:
                logger.warning(
                    "Seize VLS-only: FCLASS=8 echoue ({})",
                    r1.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ") or "(vide)",
                )
            r2 = _at(_TAD_OFF_HOOK)
            self.serial_connection.timeout = old_t
            raw = r2.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ")
            logger.info("Seize sync VLS-only AT+VLS=1 -> {}", raw or "(vide)")
            vls_ok = b"OK" in r2
            if vls_ok:
                self._flush_serial_rx_sync()
                self._configure_voice_after_seize_sync()
            return vls_ok
        except Exception as e:
            logger.warning("Seize VLS-only echec: {}", e)
            return False

    def _voice_seize_sync_unlocked(self, *, fast: bool = False, skip_ata: bool = False) -> bool:
        """
        Decroche l'appel entrant le plus vite possible (ATA operateur + mode voix).

        ATA est indispensable sur lignes FR (SFR, etc.) : VLS=1 seul coupe le fixe
        parallele mais l'operateur peut encore basculer sur sa messagerie reseau.

        A appeler sous ``_serial_io_lock``.

        @returns True si decrochage operateur ou VLS=1 OK.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return False
        try:
            old_t = self.serial_connection.timeout
            read_timeout = 0.10 if fast else 0.35
            at_deadline = 0.35 if fast else 0.65
            ata_extra = 0.35 if fast else 0.5
            self.serial_connection.timeout = read_timeout

            def _at(cmd: str, *, extra: float = 0.0, ring_grace: bool = False) -> bytes:
                self.serial_connection.write(f"{cmd}\r\n".encode())
                self.serial_connection.flush()
                deadline = time.monotonic() + at_deadline + extra
                buf = b""
                while time.monotonic() < deadline:
                    chunk = self.serial_connection.read(128) or b""
                    if chunk:
                        buf += chunk
                        upper = buf.upper()
                        if b"OK" in buf or b"CONNECT" in upper:
                            break
                        if b"NO CARRIER" in upper and b"OK" not in buf and b"CONNECT" not in upper:
                            break
                        if b"ERROR" in buf and b"OK" not in buf and b"CONNECT" not in upper:
                            break
                        if ring_grace and b"RING" in upper and b"OK" not in buf and b"CONNECT" not in upper:
                            deadline = max(deadline, time.monotonic() + 0.55)
                            continue
                    else:
                        time.sleep(0.01)
                return buf

            # 1) ATA : le reseau (SFR) voit un vrai decrochage, pas seulement un off-hook local.
            ata_ok = False
            if not skip_ata:
                r_ata = _at("ATA", extra=ata_extra, ring_grace=True)
                ata_ok = b"OK" in r_ata or b"CONNECT" in r_ata.upper()
                if ata_ok:
                    logger.info("Seize sync ATA -> decrochage operateur OK")
                else:
                    logger.warning(
                        "Seize sync ATA sans OK/CONNECT ({}) — essai mode voix direct",
                        r_ata.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ") or "(vide)",
                    )

            # 2) Mode voix pour TTS / enregistrement
            r1 = _at(_VOICE_MODE)
            fclass_ok = b"OK" in r1
            if not fclass_ok and not ata_ok:
                logger.warning(
                    "Seize sync: FCLASS=8 echoue ({}) — poursuite vers VLS",
                    r1.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ") or "(vide)",
                )
            r2 = _at(_TAD_OFF_HOOK)
            self.serial_connection.timeout = old_t
            raw = r2.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ")
            logger.info("Seize sync AT+VLS=1 -> {}", raw or "(vide)")
            vls_ok = b"OK" in r2
            ok = ata_ok or vls_ok
            if ok:
                self._flush_serial_rx_sync()
                self._configure_voice_after_seize_sync()
            elif not ata_ok:
                logger.warning("Seize sync incomplet (ATA et VLS non confirmes)")
                self._send_command_sync("ATH")
                time.sleep(0.08)
                r_retry = _at(_TAD_OFF_HOOK, extra=0.25)
                if b"OK" in r_retry:
                    logger.info("Seize sync retry AT+VLS=1 -> OK")
                    self._flush_serial_rx_sync()
                    self._configure_voice_after_seize_sync()
                    ok = True
            return ok
        except Exception as e:
            logger.warning("Seize sync echec: {}", e)
            return False

    def consume_incoming_seize(self) -> Optional[bool]:
        """
        Si un seize sync a deja ete fait au RING, renvoie son succes et consomme le flag.

        @returns True/False si seize fait, None sinon.
        """
        if not self._incoming_line_seized:
            return None
        ok = bool(self._incoming_seize_ok)
        self._incoming_line_seized = False
        self._incoming_seize_ok = False
        return ok

    def clear_incoming_seize(self) -> None:
        """Reset flags seize (fin d'appel / hangup)."""
        had_seize = bool(self._incoming_line_seized or self._incoming_seize_ok or self._voice_line_ready)
        self.log_voice_session("clear_seize", had=int(had_seize))
        self._incoming_line_seized = False
        self._incoming_seize_ok = False
        self._voice_line_ready = False
        self._greeting_played_on_seize = False
        self._early_greeting_pending = False
        self._reset_voice_session_flags()
        task = self._deferred_seize_task
        self._deferred_seize_task = None
        if task and not task.done():
            task.cancel()
        early = self._early_greeting_task
        self._early_greeting_task = None
        if early and not early.done():
            early.cancel()

    def set_early_greeting_wav(self, wav_path: Optional[Path], *, enabled: bool) -> None:
        """
        Configure le WAV d'accueil a jouer immediatement apres seize au RING.

        @param wav_path Fichier 8 kHz pret modem, ou None pour desactiver.
        @param enabled True si instant_ring_seize actif.
        """
        self.early_greeting_wav = wav_path if wav_path and wav_path.is_file() else None
        self.early_greeting_enabled = bool(enabled and self.early_greeting_wav)

    def _play_early_greeting_sync(self) -> bool:
        """
        Joue l'accueil cache sous lock serie (executor / thread modem).

        @returns True si lecture VTX complete sans interruption.
        """
        if not self.early_greeting_enabled or not self.early_greeting_wav:
            return False
        if not self._incoming_seize_ok:
            return False
        if not self._voice_line_ready:
            self._prepare_voice_line_after_seize_sync()
        logger.info("Accueil immediat post-seize: {}", self.early_greeting_wav.name)
        ok = self._play_wav_serial_impl(self.early_greeting_wav, already_in_voice_mode=True)
        if ok:
            logger.info("Accueil immediat post-seize termine")
        else:
            logger.warning("Accueil immediat post-seize echoue ou interrompu")
        return ok

    async def wait_early_greeting_done(self, timeout: float = 45.0) -> None:
        """
        Attend la fin de l'accueil lance au seize (si encore en cours).

        @param timeout Secondes max.
        """
        deadline = time.monotonic() + min(timeout, 60.0)
        while self._early_greeting_pending and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        task = self._early_greeting_task
        if not task or task.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=max(0.1, deadline - time.monotonic()))
        except asyncio.TimeoutError:
            logger.warning("Timeout attente accueil immediat ({:.0f}s)", timeout)
        except asyncio.CancelledError:
            return

    def early_greeting_was_scheduled(self) -> bool:
        """
        True si l'accueil immediat etait actif pour cet appel (evite double VTX).

        @returns Etat modem early_greeting_enabled.
        """
        return bool(self.early_greeting_enabled)

    def _try_voice_seize_now(self, reason: str) -> None:
        """
        Seize voix sous lock si pas deja off-hook (coupe sonnerie).

        @param reason Motif log (cid|grace|ring).
        """
        if self._incoming_line_seized or self._outgoing_owns_serial:
            return
        if not self.serial_connection or not self.serial_connection.is_open:
            return
        logger.info("Seize sync ({}) - coupe sonnerie", reason)
        ok = False
        if reason == "ring":
            # Call Attendant : VLS d'abord (rapide), ATA seulement en secours.
            ok = self._voice_seize_vls_only_sync_unlocked(fast=True)
            if not ok:
                logger.info("Seize VLS-only echoue — essai ATA + voix")
                ok = self._voice_seize_sync_unlocked(fast=True, skip_ata=False)
            if not ok:
                logger.info("Seize sync retry complet (ATA lent)")
                ok = self._voice_seize_sync_unlocked(fast=False, skip_ata=False)
        else:
            ok = self._voice_seize_sync_unlocked(fast=(reason == "ring"))
            if not ok and reason == "ring":
                logger.info("Seize sync retry immediat (ring)")
                ok = self._voice_seize_sync_unlocked(fast=False)
        self._incoming_line_seized = True
        self._incoming_seize_ok = ok

    async def _deferred_instant_seize_after_cid_grace(self) -> None:
        """
        Apres un RING en mode coupe-sonnerie : attend brièvement NMBR= puis VLS=1.

        Sur ligne FR (CID apres 1er ring), ~0.6-1.0s suffisent souvent pour le numero
        sans laisser sonner le fixe plusieurs fois.
        """
        grace = max(0.2, float(self.instant_seize_cid_grace_sec or 1.0))
        deadline = time.monotonic() + grace
        try:
            while time.monotonic() < deadline:
                if self._incoming_line_seized or self._outgoing_owns_serial:
                    return
                if self.last_cid_raw and normalize_cid_value(self.last_cid_raw):
                    break
                await asyncio.sleep(0.05)
            if self._incoming_line_seized or self._outgoing_owns_serial:
                return
            async with self._serial_io_lock:
                self._try_voice_seize_now("grace_cid")
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("Seize differe echoue: {}", exc)

    async def _process_modem_line(self, line: bytes):
        """
        Traite une ligne reçue du modem.

        Les callbacks entrants sont lances en tache (pas d'await bloquant) :
        sinon l'attente CID dans CallManager empêche de lire NMBR=/NAME=.

        @param line Ligne de données du modem.
        """
        line_str = line.decode("utf-8", errors="ignore").strip()
        logger.debug("Ligne modem: {}", line_str)

        dtmf = extract_incoming_dtmf_digit(line_str)
        if dtmf and self._dtmf_event is not None:
            self._dtmf_last_digit = dtmf
            self._dtmf_event.set()
            logger.info("DTMF entrant detecte: {}", dtmf)

        async def _notify(**kwargs) -> None:
            cb = self.on_incoming_call
            if not cb:
                return
            try:
                await cb(**kwargs)
            except Exception as exc:
                logger.exception("Callback appel entrant: {}", exc)

        # Detecter un appel entrant (RING)
        if "RING" in line_str.upper() and not line_str.upper().startswith("NMBR"):
            if line_str.strip().upper() == "RING" or line_str.strip().upper().startswith("RING"):
                self.last_ring_at = time.time()
                logger.info("Appel entrant détecté!")
                asyncio.create_task(_notify(), name="vg_incoming_ring")

        # Caller ID : NMBR= / NAME= (parfois prefixe espaces, parfois dans une ligne mixte)
        date_m = re.search(r"DATE\s*=\s*(\S+)", line_str, flags=re.IGNORECASE)
        time_m = re.search(r"TIME\s*=\s*(\S+)", line_str, flags=re.IGNORECASE)
        if date_m or time_m:
            logger.debug(
                "CID meta DATE={} TIME={}",
                date_m.group(1) if date_m else "-",
                time_m.group(1) if time_m else "-",
            )

        nmbr_m = re.search(r"NMBR\s*=\s*([^\r\n]+)", line_str, flags=re.IGNORECASE)
        if nmbr_m:
            raw = nmbr_m.group(1).strip().strip('"').strip("'")
            self.last_cid_raw = raw
            caller_id = normalize_cid_value(raw)
            if caller_id:
                logger.info("Caller ID: {}", caller_id)
                # Des que le numero arrive : seize tout de suite (coupe sonnerie).
                if self.instant_ring_seize and not self._incoming_line_seized and not self._outgoing_owns_serial:
                    async with self._serial_io_lock:
                        self._try_voice_seize_now("cid")
                asyncio.create_task(_notify(caller_id=caller_id), name="vg_incoming_cid")
            else:
                logger.info("Caller ID masque ignore: NMBR={}", raw)

        name_m = re.search(r"NAME\s*=\s*([^\r\n]+)", line_str, flags=re.IGNORECASE)
        if name_m:
            raw_name = name_m.group(1).strip().strip('"').strip("'")
            caller_name = normalize_cid_value(raw_name)
            if caller_name:
                logger.info("Caller NAME: {}", caller_name)
                asyncio.create_task(_notify(caller_name=caller_name), name="vg_incoming_name")
            else:
                logger.info("Caller NAME masque ignore: NAME={}", raw_name)
    
    def close(self):
        """Ferme la connexion au modem"""
        self._close_serial()
        self.is_initialized = False
        logger.info("Connexion modem fermee")

