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
from pathlib import Path
from typing import Optional, Tuple

import serial
from loguru import logger

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
_DTE_END_VOICE_TX = (chr(16) + chr(3)).encode()  # DLE ETX (USR)
_DTE_END_VOICE_TX_CONEXANT = (chr(16) * 3 + chr(3)).encode()   # DLE DLE DLE ETX (Conexant)
_DTE_END_VOICE_RX_CONEXANT = (chr(16) * 3 + chr(33)).encode()   # DLE DLE DLE ! (Conexant)
_VRX_SAMPLE_RATE = 8000
_VRX_BYTES_PER_SEC = 8000  # 8 kHz, 8-bit mono


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
            await self.send_command("ATE0")  # Désactiver l'écho
            await self.send_command("AT+VCID=1")  # Activer le Caller ID
            
            # Type de modem : Conexant / USR 5637 = mode voix série supporté
            response_ati = await self.send_command_full("ATI", timeout=2.0)
            response_ati0 = await self.send_command_full("ATI0", timeout=2.0)
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
            logger.info("Modem initialisé avec succès")
            return True
            
        except Exception as e:
            # Pas de traceback complet : erreur courante en dev (mauvais port, OS sans /dev/ttyACM0).
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
        if not self.port:
            return False
        async with self._serial_io_lock:
            self._close_serial()
        try:
            await asyncio.sleep(0.5)
            async with self._serial_io_lock:
                self.serial_connection = serial.Serial(
                    self.port,
                    self.baudrate,
                    timeout=1,
                    write_timeout=1,
                )
            await asyncio.sleep(0.8)
            await self.send_command("AT", _retry=False)
            await self.send_command("ATE0", _retry=False)
            await self.send_command("AT+VCID=1", _retry=False)
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
        nmbr = re.search(r"NMBR=(\S+)", text)
        name = re.search(r"NAME=(\S+)", text)
        return (
            nmbr.group(1).strip() if nmbr else None,
            name.group(1).strip() if name else None,
        )

    async def answer_call(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Decroche l'appel entrant.
        Essaie ATA (reponse OK ou CONNECT), puis ATH1 (off-hook) si besoin.
        Retourne (succes, caller_id, caller_name) ; caller_id/name peuvent etre remplis
        si le modem envoie NMBR=/NAME= dans la reponse a ATA.
        """
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
    
    async def hangup(self) -> bool:
        """
        Raccroche l'appel. En cas d'erreur I/O, tente une reconnexion puis renvoie ATH.
        """
        try:
            response = await self.send_command("ATH")
            return b"OK" in response
        except (OSError, serial.SerialException, RuntimeError) as e:
            if getattr(e, "errno", None) == errno.EIO or isinstance(e, serial.SerialException):
                logger.warning("EIO au raccrochage, reconnexion puis nouvel essai ATH")
                if await self.reconnect():
                    try:
                        r = await self.send_command("ATH")
                        return b"OK" in r
                    except Exception:
                        pass
            logger.error("Erreur lors du raccrochage: {}", e)
            return False
        except Exception as e:
            logger.error("Erreur lors du raccrochage: {}", e)
            return False

    async def dial_number(self, phone_number: str, timeout: float = 25.0) -> tuple[bool, str]:
        """
        Compose un numero sortant via ATD et attend un etat modem.

        @param phone_number Numero a composer.
        @param timeout Delai max d'attente de reponse modem.
        @returns Tuple (succes, reponse_brute).
        """
        if not phone_number:
            return (False, "numero vide")
        command = f"ATD{phone_number};"
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
        response = await self.send_command(f'AT+VTS="{clean}"', timeout=3.0)
        return b"OK" in response

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
                # Certains modems Conexant acceptent le format USR (128,8000) et refusent 1,8000,0,0
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
                # Envoyer les trames PCM en temps reel : 1024 octets = 128 ms a 8 kHz
                chunk = 1024
                sleep_interval = chunk / float(framerate) if framerate else 0.128
                logger.info("Lecture WAV vers ligne (VTX), chunk={} sleep={:.3f}s", chunk, sleep_interval)
                data = wf.readframes(chunk)
                while data:
                    if sampwidth == 2:  # 16-bit signed LE -> 8-bit unsigned (128 = silence)
                        out = []
                        for i in range(0, len(data), 2):
                            sample = int.from_bytes(data[i : i + 2], "little", signed=True)
                            out.append(max(0, min(255, (sample >> 8) + 128)))
                        data = bytes(out)
                    self.serial_connection.write(data)
                    data = wf.readframes(chunk)
                    time.sleep(sleep_interval)
                end_seq = _DTE_END_VOICE_TX_CONEXANT if self._is_conexant else _DTE_END_VOICE_TX
                self.serial_connection.write(end_seq)
                self.serial_connection.flush()
            return True
        except Exception as e:
            logger.exception("Erreur lecture WAV via serie: {}", e)
            return False

    def _record_wav_serial_impl(
        self, duration_sec: float, out_path: Path, already_in_voice_mode: bool = False
    ) -> bool:
        """
        Enregistre l'audio depuis la ligne telephonique via le mode voix (AT+VRX).
        Si already_in_voice_mode=True (ex. apres answer_call + play), on ne renvoie pas
        FCLASS=8 ni VLS=1 pour eviter de faire raccrocher le modem.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            logger.warning("record_wav_serial: modem non connecte")
            return False
        if not self._is_conexant:
            logger.warning("record_wav_serial: modem non Conexant, VRX non garanti")
        try:
            if not already_in_voice_mode:
                if not self._send_command_sync(_VOICE_MODE):
                    logger.warning("record_wav_serial: AT+FCLASS=8 a echoue")
                    return False
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
            logger.info("Enregistrement ligne (VRX) pendant {} s...", duration_sec)
            chunks = []
            deadline = time.monotonic() + duration_sec
            old_timeout = self.serial_connection.timeout
            self.serial_connection.timeout = 0.2
            io_error = False
            try:
                while time.monotonic() < deadline:
                    if not self.serial_connection or not self.serial_connection.is_open:
                        logger.warning("Enregistrement VRX interrompu: port serie ferme")
                        break
                    try:
                        n = self.serial_connection.in_waiting
                        if n > 0:
                            chunks.append(self.serial_connection.read(n))
                        else:
                            time.sleep(0.02)
                    except (OSError, serial.SerialException) as e:
                        logger.warning("Enregistrement VRX I/O erreur (modem deconnecte?): {}", e)
                        io_error = True
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
        """Ferme le flux VRX transparent et restaure le timeout serie."""
        self._vrx_transparent_close_sync()
        try:
            if self.serial_connection and self.serial_connection.is_open and self._vrx_saved_timeout is not None:
                self.serial_connection.timeout = self._vrx_saved_timeout
        except (OSError, serial.SerialException):
            pass
        self._vrx_saved_timeout = None

    def _half_duplex_uplink_sync(self, u8_pcm: bytes) -> bool:
        """
        Coupe VRX, envoie une rafale PCM 8-bit 8 kHz vers la ligne (VTX), rouvre VRX.
        Utilise pour micro navigateur lorsqu'il n'y a pas de carte ALSA modem.
        """
        if not u8_pcm or not self.serial_connection or not self.serial_connection.is_open:
            return True
        try:
            self._vrx_transparent_close_sync()
            vsd = _VSD_DISABLE_CONEXANT if self._is_conexant else _VSD_DISABLE_USR
            self._send_command_sync(vsd)
            if self._is_conexant:
                if not self._send_command_sync(_VOICE_COMPRESSION_USR):
                    self._send_command_sync(_VOICE_COMPRESSION_CONEXANT)
            else:
                self._send_command_sync(_VOICE_COMPRESSION_USR)
            if not self._send_command_sync(_VOICE_TX, expect="CONNECT", timeout=10.0):
                logger.warning("half_duplex_uplink: AT+VTX CONNECT a echoue")
                return False
            chunk = 1024
            sleep_interval = chunk / float(_VRX_SAMPLE_RATE)
            for i in range(0, len(u8_pcm), chunk):
                self.serial_connection.write(u8_pcm[i : i + chunk])
                time.sleep(sleep_interval)
            end_seq = _DTE_END_VOICE_TX_CONEXANT if self._is_conexant else _DTE_END_VOICE_TX
            self.serial_connection.write(end_seq)
            self.serial_connection.flush()
            time.sleep(0.08)
            if not self._send_command_sync(_VOICE_RX, expect="CONNECT", timeout=10.0):
                logger.warning("half_duplex_uplink: reprise AT+VRX a echoue")
                return False
            return True
        except Exception as e:
            logger.warning("half_duplex_uplink: {}", e)
            return False

    @property
    def supports_voice_serial(self) -> bool:
        """True si le modem est pret pour le mode voix serie (USR 5637 / Conexant, etc.)."""
        return bool(self.is_initialized)

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
    ) -> bool:
        """
        Enregistre l'audio depuis la ligne téléphonique via le port série (AT+VRX).
        Passer already_in_voice_mode=True si on vient de answer_call + play pour ne pas recouper l'appel.
        """
        loop = asyncio.get_event_loop()
        async with self._serial_io_lock:
            return await loop.run_in_executor(
                None,
                self._record_wav_serial_impl,
                duration_sec,
                out_path,
                already_in_voice_mode,
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

        while self.is_initialized:
            try:
                if self._outgoing_owns_serial:
                    await asyncio.sleep(0.15)
                    continue
                if not self.serial_connection.is_open:
                    logger.warning("Port série fermé, arrêt de la surveillance")
                    break
                data = b""
                async with self._serial_io_lock:
                    if not self.serial_connection or not self.serial_connection.is_open:
                        break
                    n = self.serial_connection.in_waiting
                    if n > 0:
                        chunk_size = min(n, 256)
                        data = self.serial_connection.read(chunk_size)
                if data:
                    buffer += data
                    while b"\r\n" in buffer:
                        line, buffer = buffer.split(b"\r\n", 1)
                        line = line.strip()
                        if line:
                            await self._process_modem_line(line)
                else:
                    await asyncio.sleep(0.1)
            except OSError as e:
                if not self.is_initialized or (self.serial_connection and not self.serial_connection.is_open):
                    break
                if e.errno == errno.EIO:
                    eio_count += 1
                    now = time.monotonic()
                    if now - last_eio_log >= 30.0:
                        logger.debug(
                            "EIO sur le port modem (normal sur certains USB), reprise: {} occurrences",
                            eio_count,
                        )
                        last_eio_log = now
                    await asyncio.sleep(0.5)
                else:
                    logger.error("Erreur OS sur le modem: {}", e)
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Erreur lors de la surveillance: {}", e)
                await asyncio.sleep(1)
    
    async def _process_modem_line(self, line: bytes):
        """
        Traite une ligne reçue du modem
        
        Args:
            line: Ligne de données du modem
        """
        line_str = line.decode('utf-8', errors='ignore')
        logger.debug(f"Ligne modem: {line_str}")
        
        # Détecter un appel entrant (RING)
        if 'RING' in line_str:
            logger.info("Appel entrant détecté!")
            # Notifier le callback si configuré
            if self.on_incoming_call:
                await self.on_incoming_call()
        
        # Détecter le Caller ID
        if line_str.startswith('NMBR='):
            caller_id = line_str.split('=')[1].strip()
            logger.info(f"Caller ID: {caller_id}")
            # Notifier avec le Caller ID si disponible
            if self.on_incoming_call:
                await self.on_incoming_call(caller_id=caller_id)
    
    def close(self):
        """Ferme la connexion au modem"""
        self._close_serial()
        self.is_initialized = False
        logger.info("Connexion modem fermee")

