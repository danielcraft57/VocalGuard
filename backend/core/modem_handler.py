"""
Gestionnaire de modem pour la communication téléphonique
"""

import serial
import asyncio
from typing import Optional
from loguru import logger
from pathlib import Path


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
        self.on_incoming_call: Optional[callable] = None  # Callback pour les appels entrants
    
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
            
            # Vérifier le type de modem
            response = await self.send_command("ATI")
            if b'Conexant' in response or b'CONEXANT' in response:
                logger.info("Modem Conexant détecté")
            else:
                logger.info("Modem détecté (type non identifié)")
            
            self.is_initialized = True
            logger.info("Modem initialisé avec succès")
            return True
            
        except Exception as e:
            logger.exception(f"Erreur lors de l'initialisation du modem: {e}")
            return False
    
    async def send_command(self, command: str, timeout: float = 2.0) -> bytes:
        """
        Envoie une commande AT au modem
        
        Args:
            command: Commande AT à envoyer
            timeout: Timeout en secondes
            
        Returns:
            Réponse du modem
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            raise RuntimeError("Modem non connecté")
        
        try:
            # Envoyer la commande
            cmd_bytes = f"{command}\r\n".encode()
            self.serial_connection.write(cmd_bytes)
            
            # Lire la réponse
            response = b""
            start_time = asyncio.get_event_loop().time()
            
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                if self.serial_connection.in_waiting > 0:
                    response += self.serial_connection.read(self.serial_connection.in_waiting)
                    if b'\r\n' in response:
                        break
                await asyncio.sleep(0.1)
            
            logger.debug(f"Commande: {command} -> Réponse: {response.decode('utf-8', errors='ignore')}")
            return response
            
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de la commande {command}: {e}")
            raise
    
    async def answer_call(self) -> bool:
        """
        Décroche l'appel entrant
        
        Returns:
            True si l'opération réussit
        """
        try:
            response = await self.send_command("ATA")
            return b'OK' in response
        except Exception as e:
            logger.error(f"Erreur lors du décrochage: {e}")
            return False
    
    async def hangup(self) -> bool:
        """
        Raccroche l'appel
        
        Returns:
            True si l'opération réussit
        """
        try:
            response = await self.send_command("ATH")
            return b'OK' in response
        except Exception as e:
            logger.error(f"Erreur lors du raccrochage: {e}")
            return False
    
    async def monitor_calls(self):
        """
        Surveille les appels entrants en lisant les données du modem
        """
        if not self.serial_connection:
            raise RuntimeError("Modem non initialisé")
        
        logger.info("Surveillance des appels entrants...")
        
        buffer = b""
        while self.is_initialized:
            try:
                if self.serial_connection.in_waiting > 0:
                    data = self.serial_connection.read(self.serial_connection.in_waiting)
                    buffer += data
                    
                    # Traiter les lignes complètes
                    while b'\r\n' in buffer:
                        line, buffer = buffer.split(b'\r\n', 1)
                        line = line.strip()
                        
                        if line:
                            await self._process_modem_line(line)
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Erreur lors de la surveillance: {e}")
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
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            logger.info("Connexion modem fermée")
        self.is_initialized = False

