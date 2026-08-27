"""
Gestionnaire de modem pour la communication téléphonique.

Supporte deux façons de jouer un WAV vers la ligne :
- ALSA (aplay) : le modem expose une carte son, on joue sur ce device.
- Mode voix série (comme callattendant) : commandes AT+FCLASS=8, AT+VTX puis envoi
  des trames PCM 8-bit 8 kHz sur le port série ; le modem envoie l'audio sur la ligne.
  Voir https://github.com/emxsys/callattendant (modem USR 5637 / Conexant).
"""

import asyncio
import errno
import time
import wave
import re
from functools import partial
from pathlib import Path
from typing import Optional, Tuple

import serial
from loguru import logger

from backend.core.phone_cid import normalize_cid_value
from backend.voice.audio_utils import pcm_u8_chunk_peak

# Mode voix (callattendant) : commandes AT pour jouer vers la ligne
# Voir https://github.com/emxsys/callattendant (Bruce Schubert / emxsys)
_VOICE_MODE = "AT+FCLASS=8"
_VSD_DISABLE_USR = "AT+VSD=128,0"       # desactive detection silence (USR 5637)
_VSD_DISABLE_CONEXANT = "AT+VSD=0,0"   # desactive detection silence (Zoom 3095 / Conexant)
_VOICE_COMPRESSION_USR = "AT+VSM=128,8000"       # 8-bit linear, 8 kHz (USR 5637)
_VOICE_COMPRESSION_CONEXANT = "AT+VSM=1,8000,0,0"  # 8-bit PCM, 8 kHz (Zoom 3095 / Conexant)
_TAD_OFF_HOOK = "AT+VLS=1"
_VOICE_TX = "AT+VTX"
_VOICE_RX = "AT+VRX"
_DLE = 0x10
_DTE_END_VOICE_TX = (chr(16) + chr(3)).encode()  # DLE ETX (USR)
_DTE_END_VOICE_TX_CONEXANT = (chr(16) * 3 + chr(3)).encode()   # DLE DLE DLE ETX (Conexant)
_DTE_END_VOICE_RX_CONEXANT = (chr(16) * 3 + chr(33)).encode()   # DLE DLE DLE ! (Conexant)
_VRX_SAMPLE_RATE = 8000
_VRX_BYTES_PER_SEC = 8000  # 8 kHz, 8-bit mono
_EXPECTED_FIRMWARE_HINT = "1.2.23"


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


def _vrx_buffer_has_hangup_marker(blob: bytes) -> bool:
    """
    Marqueurs AT / DLE V.253 quand le modem quitte le flux VRX (raccrochage).

    USR5637 : DLE-h = combiné local raccroche, DLE-s = silence / fin presumee,
    DLE-E / DLE ETX = fin de session voix.
    """
    if not blob:
        return False
    u = blob.upper()
    if (
        b"NO CARRIER" in u
        or b"NO ANSWER" in u
        or b"NO DIALTONE" in u
        or b"NO DIAL TONE" in u
        or b"BUSY" in u
        or b"\r\nOK\r\n" in blob
    ):
        return True
    # Fin de session voix V.253 (DLE...) apres raccrochage distant / local.
    if (
        b"\x10\x10\x10!" in blob
        or b"\x10\x10\x10\x03" in blob
        or b"\x10\x03" in blob
        or b"\x10!" in blob
        or b"\x10s" in blob  # silence / presumed hangup
        or b"\x10S" in blob
        or b"\x10h" in blob  # local on-hook (USR)
        or b"\x10H" in blob  # local off-hook (USR) - utile pour couper le repondeur
        or b"\x10b" in blob  # busy
        or b"\x10d" in blob  # dialtone (ligne libre apres raccrochage)
        or b"\x10e" in blob  # end / data calling
    ):
        return True
    return False


# Alias et helpers exposés pour tests sans matériel (scripts/modem_lab/tests/test_modem_handler_smoke.py).
_vrx_stream_contains_hangup_marker = _vrx_buffer_has_hangup_marker


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
        self.on_incoming_call: Optional[callable] = None  # Callback pour les appels entrants
        self._serial_io_lock = asyncio.Lock()
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
        # Repondeur rings=0 : seize voix apres courte fenetre CID (coupe sonnerie fixe).
        self.instant_ring_seize = False
        self._incoming_line_seized = False
        self._incoming_seize_ok = False
        self._deferred_seize_task: Optional[asyncio.Task] = None
        # Raison du dernier arret VRX (hangup_marker, silence, timeout, ...).
        self.last_vrx_stop_reason: Optional[str] = None
        # Secondes max apres RING avant VLS=1 (laisse passer NMBR= ETSI).
        self.instant_seize_cid_grace_sec: float = 0.35
    
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
            self._is_conexant = bool(
                combined
                and (
                    b"Conexant" in combined
                    or b"CONEXANT" in combined
                    or b"5601" in combined
                    or b"56000" in combined
                )
            )
            if self._is_conexant:
                logger.info("Modem Conexant/USR detecte (mode voix serie disponible)")
            else:
                logger.info("Modem detecte (type non identifie). Reponses ATI: {}", combined.decode("utf-8", errors="ignore").strip() or "(vide)")

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

    async def reconnect(self) -> bool:
        """
        Ferme et rouvre le port série après une erreur I/O (EIO).
        Réapplique les commandes AT minimales (AT, ATE0, AT+VCID=1).
        Retourne True si la reconnexion a réussi.
        """
        from pathlib import Path

        async with self._serial_io_lock:
            self._close_serial()
        try:
            await asyncio.sleep(0.5)
            # Apres reset USB le noeud peut passer de ttyACM0 a ttyACM1.
            port = self.port
            if not port or not Path(port).exists():
                detected = await self.detect_modem()
                if not detected:
                    logger.warning("Modem reconnexion: aucun port serie trouve")
                    return False
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
            await asyncio.sleep(0.8)
            await self.send_command("AT", _retry=False)
            await self.send_command("ATE0", _retry=False)
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
            logger.warning("Modem reconnexion echouee: {}", e)
            async with self._serial_io_lock:
                self._close_serial()
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
        }

    def _flush_serial_rx_sync(self) -> None:
        """
        Vide le buffer RX serie (restes RING/CID apres seize).

        Evite les faux positifs hangup pendant le premier VTX (accueil repondeur).
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return
        try:
            deadline = time.monotonic() + 0.12
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
            if self._is_conexant:
                if not self._send_command_sync(_VOICE_COMPRESSION_USR):
                    self._send_command_sync(_VOICE_COMPRESSION_CONEXANT)
            else:
                self._send_command_sync(_VOICE_COMPRESSION_USR)
        except Exception as exc:
            logger.debug("configure_voice_after_seize: {}", exc)

    async def prepare_voice_line_after_seize(self) -> None:
        """
        Apres seize sync au RING : purge RX + config voix avant l'accueil TTS.

        @returns None.
        """
        loop = asyncio.get_event_loop()
        async with self._serial_io_lock:
            await loop.run_in_executor(None, self._prepare_voice_line_after_seize_sync)

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

    def _peek_serial_interrupt_sync(self) -> bool:
        """
        Lit le buffer serie pendant VTX : hangup / pickup parallele.

        @returns True si il faut couper le playback.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return False
        try:
            if self.serial_connection.in_waiting <= 0:
                return False
            blob = self.serial_connection.read(self.serial_connection.in_waiting)
        except (OSError, serial.SerialException):
            return False
        if _vrx_buffer_has_hangup_marker(blob) or _serial_buffer_shows_remote_pickup(blob):
            logger.info("Playback interrompu (evenement ligne pendant VTX)")
            self._playback_interrupted = True
            return True
        # DLE + h / H = local hangup (tel parallele) sur beaucoup de firmwares V.253
        if b"\x10h" in blob or b"\x10H" in blob:
            logger.info("Playback interrompu (DLE hook local pendant VTX)")
            self._playback_interrupted = True
            return True
        return False

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
                ok = await loop.run_in_executor(
                    None, lambda: self._voice_seize_sync_unlocked(fast=True)
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
    
    async def hangup(self) -> bool:
        """
        Raccroche l'appel. Sort d'abord du mode voix transparent si besoin, sinon ATH
        lit du PCM et rate. En cas d'erreur I/O, tente une reconnexion puis renvoie ATH.
        """
        try:
            loop = asyncio.get_event_loop()
            async with self._serial_io_lock:
                ok = await loop.run_in_executor(None, self._force_hangup_sync)
            return ok
        except (OSError, serial.SerialException, RuntimeError) as e:
            if getattr(e, "errno", None) == errno.EIO or isinstance(e, serial.SerialException):
                logger.warning("EIO au raccrochage, reconnexion puis nouvel essai ATH")
                if await self.reconnect():
                    try:
                        loop = asyncio.get_event_loop()
                        async with self._serial_io_lock:
                            return await loop.run_in_executor(None, self._force_hangup_sync)
                    except Exception:
                        pass
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
            time.sleep(0.12)
            try:
                while self.serial_connection.in_waiting > 0:
                    self.serial_connection.read(self.serial_connection.in_waiting)
            except (OSError, serial.SerialException):
                pass

            def _ath_once() -> bytes:
                self.serial_connection.write(b"ATH\r\n")
                self.serial_connection.flush()
                deadline = time.monotonic() + 2.5
                buf = b""
                while time.monotonic() < deadline:
                    if self.serial_connection.in_waiting > 0:
                        buf += self.serial_connection.read(self.serial_connection.in_waiting)
                        if b"OK" in buf or b"ERROR" in buf:
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
                return True
            # Reponse polluee par du PCM : re-drain + 2e ATH.
            logger.warning(
                "ATH reponse suspecte ({} o), nouvel essai apres drain",
                len(resp),
            )
            self._vrx_transparent_close_sync()
            time.sleep(0.15)
            try:
                while self.serial_connection.in_waiting > 0:
                    self.serial_connection.read(min(4096, self.serial_connection.in_waiting))
            except (OSError, serial.SerialException):
                pass
            resp2 = _ath_once()
            ok = b"OK" in resp2
            # Remettre le modem en veille data + CID (evite de rester bloque en voix).
            try:
                self._send_command_sync("AT+FCLASS=0")
                self._send_command_sync("AT+VCID=1")
            except Exception:
                pass
            return ok
        except Exception as e:
            logger.warning("force_hangup: {}", e)
            try:
                self._send_command_sync("AT+FCLASS=0")
                self._send_command_sync("AT+VCID=1")
            except Exception:
                pass
            return False

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
        WAV attendu : 8 kHz, mono, 8-bit ou 16-bit (converti en 8-bit).
        Si already_in_voice_mode=True (ex. apres answer_call en mode voix), on ne renvoie pas
        FCLASS=8 ni VLS=1 pour eviter de faire raccrocher le modem.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            logger.warning("play_wav_serial: modem non connecte")
            return False
        try:
            with wave.open(str(wav_path), "rb") as wf:
                nch, sampwidth, framerate = wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
                logger.info("WAV: {} Hz, {} canaux, {} bit", framerate, nch, sampwidth * 8)
                if framerate != 8000:
                    logger.warning("WAV non 8 kHz ({} Hz), le modem peut mal jouer", framerate)
                if not already_in_voice_mode:
                    if not self._send_command_sync(_VOICE_MODE):
                        logger.warning("play_wav_serial: AT+FCLASS=8 a echoue")
                        return False
                # Desactiver la detection de silence (comme callattendant) pour eviter que le modem coupe la ligne
                vsd = _VSD_DISABLE_CONEXANT if self._is_conexant else _VSD_DISABLE_USR
                self._send_command_sync(vsd)
                self._apply_voice_gains_sync()
                # VSM : USR d'abord ; fallback Conexant seulement si modem detecte Conexant.
                vsm_ok = False
                if self._is_conexant:
                    vsm_ok = self._send_command_sync(_VOICE_COMPRESSION_USR)
                    if not vsm_ok:
                        vsm_ok = self._send_command_sync(_VOICE_COMPRESSION_CONEXANT)
                        if not vsm_ok:
                            logger.warning(
                                "play_wav_serial: VSM USR et Conexant ont echoue, on tente quand meme VTX"
                            )
                else:
                    vsm_ok = self._send_command_sync(_VOICE_COMPRESSION_USR)
                    if not vsm_ok:
                        logger.warning("play_wav_serial: AT+VSM=128,8000 a echoue, on tente quand meme VTX")
                if not already_in_voice_mode:
                    if not self._send_command_sync(_TAD_OFF_HOOK):
                        logger.warning("play_wav_serial: AT+VLS=1 a echoue")
                        return False
                if not self._send_command_sync(_VOICE_TX, expect="CONNECT", timeout=10.0):
                    logger.warning("play_wav_serial: AT+VTX (CONNECT) a echoue")
                    return False
                self._vtx_active = True
                self._playback_interrupted = False
                # Envoyer les trames PCM en temps reel : 1024 octets = 128 ms a 8 kHz
                chunk = 1024
                sleep_interval = chunk / float(framerate) if framerate else 0.128
                logger.info("Lecture WAV vers ligne (VTX), chunk={} sleep={:.3f}s", chunk, sleep_interval)
                data = wf.readframes(chunk)
                while data:
                    if self._voice_abort or self._peek_serial_interrupt_sync():
                        break
                    if sampwidth == 2:  # 16-bit signed LE -> 8-bit unsigned (128 = silence)
                        out = []
                        for i in range(0, len(data), 2):
                            sample = int.from_bytes(data[i : i + 2], "little", signed=True)
                            out.append(max(0, min(255, (sample >> 8) + 128)))
                        data = bytes(out)
                    self.serial_connection.write(_escape_dle_pcm(data))
                    data = wf.readframes(chunk)
                    time.sleep(sleep_interval)
                end_seq = _DTE_END_VOICE_TX_CONEXANT if self._is_conexant else _DTE_END_VOICE_TX
                self.serial_connection.write(end_seq)
                self.serial_connection.flush()
                self._vtx_active = False
                time.sleep(0.12)
                try:
                    while self.serial_connection.in_waiting > 0:
                        self.serial_connection.read(self.serial_connection.in_waiting)
                except (OSError, serial.SerialException):
                    pass
            return not self._playback_interrupted
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
        try:
            if not already_in_voice_mode:
                if not self._send_command_sync(_VOICE_MODE):
                    logger.warning("record_wav_serial: AT+FCLASS=8 a echoue")
                    return False
            # Detection silence logicielle (pas VSD modem) : VSD agressif a deja
            # provoque des resets USB ACM sur le hub Pi. Les marqueurs DLE suffisent.
            vsd = _VSD_DISABLE_CONEXANT if self._is_conexant else _VSD_DISABLE_USR
            self._send_command_sync(vsd)
            vsm_ok = False
            if self._is_conexant:
                vsm_ok = self._send_command_sync(_VOICE_COMPRESSION_USR)
                if not vsm_ok:
                    vsm_ok = self._send_command_sync(_VOICE_COMPRESSION_CONEXANT)
                    if not vsm_ok:
                        logger.warning(
                            "record_wav_serial: VSM USR et Conexant ont echoue, on tente quand meme VRX"
                        )
            else:
                vsm_ok = self._send_command_sync(_VOICE_COMPRESSION_USR)
                if not vsm_ok:
                    logger.warning("record_wav_serial: AT+VSM=128,8000 a echoue, on tente quand meme VRX")
            if not already_in_voice_mode:
                if not self._send_command_sync(_TAD_OFF_HOOK):
                    logger.warning("record_wav_serial: AT+VLS=1 a echoue")
                    return False
            if not self._send_command_sync(_VOICE_RX, expect="CONNECT", timeout=10.0):
                logger.warning("record_wav_serial: AT+VRX (CONNECT) a echoue")
                return False
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
            hangup_tail = bytearray()
            silence_started: Optional[float] = None
            min_record_before_silence = 0.8
            # Seuil un peu bas : apres raccrochage la ligne est souvent un souffle faible.
            effective_silence_threshold = max(8, int(silence_threshold))
            record_started = time.monotonic()
            old_timeout = self.serial_connection.timeout
            self.serial_connection.timeout = 0.2
            io_error = False
            try:
                while time.monotonic() < deadline:
                    if not self.serial_connection or not self.serial_connection.is_open:
                        logger.warning("Enregistrement VRX interrompu: port serie ferme")
                        break
                    try:
                        if stop_on_remote_hangup:
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
                            if stop_on_remote_hangup:
                                hangup_tail.extend(raw)
                                if len(hangup_tail) > 4096:
                                    del hangup_tail[:-4096]
                                if _vrx_buffer_has_hangup_marker(bytes(hangup_tail)):
                                    logger.info(
                                        "Enregistrement VRX interrompu: marqueur fin de ligne dans le flux serie"
                                    )
                                    break
                            if silence_timeout_sec > 0:
                                elapsed = time.monotonic() - record_started
                                if elapsed >= min_record_before_silence:
                                    if pcm_u8_chunk_peak(raw) >= effective_silence_threshold:
                                        silence_started = None
                                    elif silence_started is None:
                                        silence_started = time.monotonic()
                                    elif time.monotonic() - silence_started >= silence_timeout_sec:
                                        logger.info(
                                            "Enregistrement VRX interrompu: silence {} s apres la parole",
                                            silence_timeout_sec,
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
                        while self.serial_connection.in_waiting > 0:
                            chunks.append(self.serial_connection.read(self.serial_connection.in_waiting))
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
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(out_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(1)  # 8-bit
                wf.setframerate(_VRX_SAMPLE_RATE)
                wf.writeframes(data)
            logger.info("Enregistrement VRX sauve: {} ({} octets)", out_path.name, len(data))
            return True
        except Exception as e:
            logger.exception("Erreur enregistrement VRX via serie: {}", e)
            return False

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
        """Passe en mode voix et ouvre AT+VRX (flux PCM 8 kHz 8-bit)."""
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
            if self._is_conexant:
                if not self._send_command_sync(_VOICE_COMPRESSION_USR):
                    self._send_command_sync(_VOICE_COMPRESSION_CONEXANT)
            else:
                self._send_command_sync(_VOICE_COMPRESSION_USR)
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
        """Configure VSD / VSM / gains pour PCM 8-bit 8 kHz (avant VTX ou VRX)."""
        vsd = _VSD_DISABLE_CONEXANT if self._is_conexant else _VSD_DISABLE_USR
        self._send_command_sync(vsd)
        self._apply_voice_gains_sync()
        if self._is_conexant:
            if not self._send_command_sync(_VOICE_COMPRESSION_USR):
                self._send_command_sync(_VOICE_COMPRESSION_CONEXANT)
        else:
            self._send_command_sync(_VOICE_COMPRESSION_USR)

    def _vtx_begin_sync(self) -> bool:
        """
        Ferme le flux VRX et ouvre AT+VTX pour un talkspurt micro continu.

        @returns True si CONNECT VTX OK.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return False
        try:
            self._vrx_transparent_close_sync()
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
        if not u8_pcm:
            return True
        if not self._vtx_active or not self.serial_connection or not self.serial_connection.is_open:
            return False
        try:
            chunk = 512
            for i in range(0, len(u8_pcm), chunk):
                if self._voice_abort:
                    return False
                piece = u8_pcm[i : i + chunk]
                self.serial_connection.write(_escape_dle_pcm(piece))
                time.sleep(len(piece) / float(_VRX_SAMPLE_RATE))
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

        @returns True apres marqueur DLE / perte DCD / erreur I/O pendant VRX.
        """
        return self.last_vrx_stop_reason in (
            "hangup_marker",
            "hangup_dcd",
            "port_closed",
            "io_error",
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
            return await loop.run_in_executor(
                None, self._play_wav_serial_impl, wav_path, already_in_voice_mode
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
            return await loop.run_in_executor(
                None,
                partial(
                    self._record_wav_serial_impl,
                    duration_sec,
                    out_path,
                    already_in_voice_mode,
                    stop_on_remote_hangup,
                    silence_timeout_sec,
                ),
            )

    async def start_outgoing_vrx_stream(self, already_in_voice_mode: bool = False) -> bool:
        """Ouvre le flux VRX pour une session sortante (streaming vers WebSocket)."""
        loop = asyncio.get_event_loop()
        async with self._serial_io_lock:
            return await loop.run_in_executor(None, self._vrx_stream_open_sync, already_in_voice_mode)

    async def end_outgoing_vrx_stream(self) -> None:
        """Ferme le flux VRX (avant ATH)."""
        loop = asyncio.get_event_loop()
        async with self._serial_io_lock:
            await loop.run_in_executor(None, self._vrx_stream_finalize_sync)

    async def read_outgoing_vrx_chunk(self, nbytes: int = 2048) -> bytes:
        """Lit des octets PCM 8-bit depuis le flux VRX (lock court)."""
        loop = asyncio.get_event_loop()
        async with self._serial_io_lock:
            return await loop.run_in_executor(None, self._serial_read_fixed, nbytes)

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
        loop = asyncio.get_event_loop()
        async with self._serial_io_lock:
            return await loop.run_in_executor(None, self._half_duplex_uplink_sync, u8_pcm)

    async def begin_outgoing_vtx(self) -> bool:
        """
        Ouvre un talkspurt micro (ferme VRX, AT+VTX).

        @returns True si VTX pret.
        """
        loop = asyncio.get_event_loop()
        async with self._serial_io_lock:
            return await loop.run_in_executor(None, self._vtx_begin_sync)

    async def write_outgoing_vtx_u8(self, u8_pcm: bytes) -> bool:
        """
        Ecrit du PCM pendant un talkspurt VTX deja ouvert.

        @param u8_pcm PCM 8-bit 8 kHz.
        @returns True si ecriture OK.
        """
        if not u8_pcm:
            return True
        loop = asyncio.get_event_loop()
        async with self._serial_io_lock:
            return await loop.run_in_executor(None, self._vtx_write_paced_sync, u8_pcm)

    async def end_outgoing_vtx_reopen_vrx(self) -> bool:
        """
        Ferme le talkspurt VTX et rouvre VRX.

        @returns True si VRX repris.
        """
        loop = asyncio.get_event_loop()
        async with self._serial_io_lock:
            return await loop.run_in_executor(None, self._vtx_end_reopen_vrx_sync)

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
                            await self._process_modem_line(line)
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

    def _voice_seize_sync_unlocked(self, *, fast: bool = False) -> bool:
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

            def _at(cmd: str, *, extra: float = 0.0) -> bytes:
                self.serial_connection.write(f"{cmd}\r\n".encode())
                self.serial_connection.flush()
                deadline = time.monotonic() + at_deadline + extra
                buf = b""
                while time.monotonic() < deadline:
                    chunk = self.serial_connection.read(128) or b""
                    if chunk:
                        buf += chunk
                        upper = buf.upper()
                        if (
                            b"OK" in buf
                            or b"ERROR" in buf
                            or b"CONNECT" in upper
                            or b"NO CARRIER" in upper
                        ):
                            break
                    else:
                        time.sleep(0.01)
                return buf

            # 1) ATA : le reseau (SFR) voit un vrai decrochage, pas seulement un off-hook local.
            r_ata = _at("ATA", extra=ata_extra)
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
            if b"OK" not in r1 and not ata_ok:
                logger.warning(
                    "Seize sync: FCLASS=8 echoue ({})",
                    r1.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ") or "(vide)",
                )
                self.serial_connection.timeout = old_t
                return False
            r2 = _at(_TAD_OFF_HOOK)
            self.serial_connection.timeout = old_t
            raw = r2.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ")
            logger.info("Seize sync AT+VLS=1 -> {}", raw or "(vide)")
            vls_ok = b"OK" in r2
            ok = ata_ok or vls_ok
            if ok:
                self._flush_serial_rx_sync()
                self._configure_voice_after_seize_sync()
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
        self._incoming_line_seized = False
        self._incoming_seize_ok = False
        task = self._deferred_seize_task
        self._deferred_seize_task = None
        if task and not task.done():
            task.cancel()

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
        ok = self._voice_seize_sync_unlocked(fast=(reason == "ring"))
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

