"""
Service de détection de numéros commerciaux et télémarketeurs
Inspiré de callattendant (https://github.com/emxsys/callattendant)
"""

import re
from typing import Dict, List, Optional, Tuple
from loguru import logger


class CommercialDetector:
    """
    Détecte les numéros commerciaux et télémarketeurs basé sur des patterns
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialise le détecteur commercial
        
        Args:
            config: Configuration optionnelle avec patterns personnalisés
        """
        self.config = config or {}
        
        # Patterns de numéros commerciaux (comme dans callattendant)
        self.number_patterns = self.config.get('number_patterns', {})
        self.name_patterns = self.config.get('name_patterns', {})
        
        # Patterns par défaut pour la France
        self._init_default_patterns()
    
    def _init_default_patterns(self):
        """
        Initialise les patterns par défaut pour la détection commerciale
        """
        # Patterns de numéros commerciaux français
        if not self.number_patterns:
            self.number_patterns = {
                # Numéros surtaxés (08XX)
                r'^(\+33|0)8[0-9]{2}[0-9]{6}$': 'Numéro surtaxé',
                # Numéros à valeur ajoutée (09XX)
                r'^(\+33|0)9[0-9]{2}[0-9]{6}$': 'Numéro à valeur ajoutée',
                # Numéros verts (0800, 0801, 0802, 0803, 0804, 0805)
                r'^(\+33|0)80[0-5][0-9]{6}$': 'Numéro vert',
                # Numéros indigo (0820, 0821, 0825)
                r'^(\+33|0)82[015][0-9]{6}$': 'Numéro indigo',
                # Numéros azur (0810, 0811, 0812, 0813, 0814, 0815)
                r'^(\+33|0)81[0-5][0-9]{6}$': 'Numéro azur',
                # Numéros kiosque (089X)
                r'^(\+33|0)89[0-9]{7}$': 'Numéro kiosque',
            }
        
        # Patterns de noms de télémarketeurs (comme dans callattendant)
        if not self.name_patterns:
            self.name_patterns = {
                # Pattern V suivi de 15 chiffres (télémarketeurs)
                r'V[0-9]{15}': 'Télémarketeur (Caller ID)',
                # Patterns de noms commerciaux courants
                r'^(SERVICE|SERV|SRV|CALL|TEL|PHONE)': 'Service commercial',
                r'^(MARKETING|MARKET|MKT)': 'Marketing',
                r'^(PUBLICIT|PUB|ADV)': 'Publicité',
                r'^(TELEMARKET|TELESALES|TELESELL)': 'Télémarketing',
                r'^(SALES|VENTE|COMMERCIAL)': 'Vente',
                r'^(SUPPORT|ASSISTANCE|HELP)': 'Support commercial',
                r'^(INFO|INFORMATION)': 'Service d\'information',
                r'^(PROMO|PROMOTION)': 'Promotion',
                r'^(OFFER|OFFRE)': 'Offre commerciale',
                r'^(SURVEY|ENQUETE|SONDAGE)': 'Enquête',
                r'^(ROBOCALL|ROBOT|AUTO)': 'Appel automatisé',
                r'^(SPAM|SCAM|FRAUD)': 'Spam/Scam',
                r'^[A-Z]{1,3}[0-9]{10,}$': 'Pattern suspect (lettres + chiffres)',
            }
    
    def detect_commercial(self, phone_number: Optional[str] = None, 
                         caller_name: Optional[str] = None) -> Dict[str, any]:
        """
        Détecte si un appel est commercial
        
        Args:
            phone_number: Numéro de téléphone
            caller_name: Nom de l'appelant
            
        Returns:
            Dictionnaire avec les informations de détection
        """
        result = {
            'is_commercial': False,
            'is_telemarketer': False,
            'detection_type': None,
            'pattern_matched': None,
            'description': None,
            'confidence': 0.0,
        }
        
        # Vérifier les patterns de numéros
        if phone_number:
            number_match = self._check_number_patterns(phone_number)
            if number_match:
                result['is_commercial'] = True
                result['detection_type'] = 'number_pattern'
                result['pattern_matched'] = number_match['pattern']
                result['description'] = number_match['description']
                result['confidence'] = 0.8
        
        # Vérifier les patterns de noms
        if caller_name:
            name_match = self._check_name_patterns(caller_name)
            if name_match:
                result['is_commercial'] = True
                result['is_telemarketer'] = True
                result['detection_type'] = 'name_pattern'
                result['pattern_matched'] = name_match['pattern']
                result['description'] = name_match['description']
                result['confidence'] = 0.9
        
        # Si les deux correspondent, augmenter la confiance
        if result.get('detection_type') == 'number_pattern' and name_match:
            result['confidence'] = 0.95
        
        return result
    
    def _check_number_patterns(self, phone_number: str) -> Optional[Dict[str, str]]:
        """
        Vérifie si le numéro correspond à un pattern commercial
        
        Args:
            phone_number: Numéro à vérifier
            
        Returns:
            Dictionnaire avec pattern et description si match, None sinon
        """
        # Nettoyer le numéro
        clean_number = re.sub(r'[^\d+]', '', phone_number)
        
        # Normaliser pour la France (ajouter +33 si commence par 0)
        if clean_number.startswith('0') and not clean_number.startswith('+33'):
            clean_number = '+33' + clean_number[1:]
        
        for pattern, description in self.number_patterns.items():
            try:
                if re.match(pattern, clean_number, re.IGNORECASE):
                    logger.debug(f"Pattern commercial détecté: {pattern} -> {description}")
                    return {
                        'pattern': pattern,
                        'description': description
                    }
            except re.error as e:
                logger.warning(f"Pattern regex invalide: {pattern} - {e}")
        
        return None
    
    def _check_name_patterns(self, caller_name: str) -> Optional[Dict[str, str]]:
        """
        Vérifie si le nom correspond à un pattern commercial
        
        Args:
            caller_name: Nom à vérifier
            
        Returns:
            Dictionnaire avec pattern et description si match, None sinon
        """
        if not caller_name:
            return None
        
        caller_name_upper = caller_name.upper().strip()
        
        for pattern, description in self.name_patterns.items():
            try:
                if re.search(pattern, caller_name_upper):
                    logger.debug(f"Pattern nom commercial détecté: {pattern} -> {description}")
                    return {
                        'pattern': pattern,
                        'description': description
                    }
            except re.error as e:
                logger.warning(f"Pattern regex invalide: {pattern} - {e}")
        
        return None
    
    def is_french_commercial_prefix(self, phone_number: str) -> bool:
        """
        Vérifie si un numéro français est un préfixe commercial connu
        
        Args:
            phone_number: Numéro à vérifier
            
        Returns:
            True si c'est un préfixe commercial
        """
        clean_number = re.sub(r'[^\d+]', '', phone_number)
        
        # Normaliser pour la France
        if clean_number.startswith('0') and not clean_number.startswith('+33'):
            clean_number = '+33' + clean_number[1:]
        
        # Préfixes commerciaux français
        commercial_prefixes = [
            '0800', '0801', '0802', '0803', '0804', '0805',  # Numéros verts
            '0810', '0811', '0812', '0813', '0814', '0815',  # Numéros azur
            '0820', '0821', '0825',  # Numéros indigo
            '0890', '0891', '0892', '0893', '0894', '0895', '0896', '0897', '0898', '0899',  # Numéros kiosque
        ]
        
        # Vérifier les préfixes
        for prefix in commercial_prefixes:
            if clean_number.startswith('+33' + prefix) or clean_number.startswith('0' + prefix):
                return True
        
        # Vérifier les numéros surtaxés (08XX sauf ceux déjà listés)
        if re.match(r'^(\+33|0)8[0-9]{2}', clean_number):
            # Exclure les numéros verts, azur, indigo et kiosque déjà vérifiés
            if not re.match(r'^(\+33|0)(080[0-5]|081[0-5]|082[015]|089[0-9])', clean_number):
                return True
        
        # Vérifier les numéros à valeur ajoutée (09XX)
        if re.match(r'^(\+33|0)9[0-9]{2}', clean_number):
            return True
        
        return False
    
    def add_custom_pattern(self, pattern: str, description: str, 
                          pattern_type: str = 'number') -> bool:
        """
        Ajoute un pattern personnalisé
        
        Args:
            pattern: Pattern regex
            description: Description du pattern
            pattern_type: 'number' ou 'name'
            
        Returns:
            True si ajouté avec succès
        """
        try:
            # Tester le pattern
            re.compile(pattern)
            
            if pattern_type == 'number':
                self.number_patterns[pattern] = description
            elif pattern_type == 'name':
                self.name_patterns[pattern] = description
            else:
                logger.warning(f"Type de pattern invalide: {pattern_type}")
                return False
            
            logger.info(f"Pattern {pattern_type} ajouté: {pattern} -> {description}")
            return True
            
        except re.error as e:
            logger.error(f"Pattern regex invalide: {pattern} - {e}")
            return False
    
    def get_patterns(self) -> Dict[str, Dict[str, str]]:
        """
        Retourne tous les patterns configurés
        
        Returns:
            Dictionnaire avec number_patterns et name_patterns
        """
        return {
            'number_patterns': self.number_patterns,
            'name_patterns': self.name_patterns
        }

