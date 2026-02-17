"""
Détecteur de numéros français avec identification de l'opérateur, ville et région
"""

import re
from pathlib import Path
from typing import Dict, Optional, Tuple
from loguru import logger
from sqlalchemy.orm import Session

from backend.services.french_phone_data import FrenchPhoneDataManager
from backend.services.french_phone_db import FrenchPhoneDatabase


class FrenchPhoneDetector:
    """
    Détecte l'opérateur, la ville et la région pour les numéros français
    """
    
    def __init__(self, data_path: Optional[Path] = None, db: Optional[Session] = None):
        """
        Initialise le détecteur français
        
        Args:
            data_path: Chemin vers le dossier de données (optionnel)
            db: Session de base de données (optionnel)
        """
        # Initialiser le gestionnaire de données JSON
        if data_path is None:
            data_path = Path.home() / ".vocalguard" / "french_phone_data"
        self.data_manager = FrenchPhoneDataManager(data_path)
        
        # Initialiser le gestionnaire de base de données
        self.db_manager = FrenchPhoneDatabase(db)
        
        # Garder les mappings de base pour compatibilité
        self._init_region_mapping()
        self._init_operator_mapping()
        self._init_city_mapping()
    
    def _init_region_mapping(self):
        """
        Initialise le mapping des indicatifs régionaux français
        """
        self.region_mapping = {
            '01': {
                'region': 'Île-de-France',
                'cities': ['Paris', 'Créteil', 'Versailles', 'Nanterre', 'Bobigny'],
                'description': 'Paris et région parisienne'
            },
            '02': {
                'region': 'Nord-Ouest',
                'cities': ['Rouen', 'Caen', 'Rennes', 'Nantes', 'Brest', 'Le Mans', 'Angers', 'Tours', 'Orléans'],
                'description': 'Nord-Ouest (Bretagne, Centre-Val de Loire, Normandie, Pays de la Loire) + Océan Indien'
            },
            '03': {
                'region': 'Nord-Est',
                'cities': ['Metz', 'Nancy', 'Strasbourg', 'Mulhouse', 'Colmar', 'Épinal', 'Vesoul', 'Belfort', 'Besançon', 'Reims', 'Troyes', 'Dijon', 'Lille', 'Amiens'],
                'description': 'Nord-Est (Bourgogne-Franche-Comté, Grand Est, Hauts-de-France)'
            },
            '04': {
                'region': 'Sud-Est',
                'cities': ['Lyon', 'Grenoble', 'Saint-Étienne', 'Clermont-Ferrand', 'Annecy', 'Chambéry', 'Marseille', 'Nice', 'Toulon', 'Avignon', 'Montpellier', 'Perpignan', 'Nîmes', 'Ajaccio', 'Bastia'],
                'description': 'Sud-Est (Auvergne-Rhône-Alpes, Corse, Provence-Alpes-Côte d\'Azur, Occitanie Languedoc-Roussillon)'
            },
            '05': {
                'region': 'Sud-Ouest',
                'cities': ['Bordeaux', 'Toulouse', 'Limoges', 'Pau', 'Bayonne', 'La Rochelle', 'Poitiers', 'Tarbes', 'Albi', 'Montauban'],
                'description': 'Sud-Ouest (Nouvelle-Aquitaine, Occitanie Midi-Pyrénées) + DOM (Guadeloupe, Martinique, Guyane)'
            },
        }
    
    def _init_operator_mapping(self):
        """
        Initialise le mapping des opérateurs français basé sur les préfixes
        Note: Avec la portabilité des numéros, c'est moins fiable mais donne des indices
        Source: https://fr.wikipedia.org/wiki/Liste_des_préfixes_des_opérateurs_de_téléphonie_mobile_en_France
        """
        # Préfixes mobiles par opérateur (basé sur les attributions ARCEP)
        # Format: préfixe ABPQ (4 chiffres après 06 ou 07) -> opérateur
        # Source: https://fr.wikipedia.org/wiki/Liste_des_préfixes_des_opérateurs_de_téléphonie_mobile_en_France
        # Note: La portabilité rend ces attributions indicatives
        self.mobile_prefixes = {
            # Préfixes de routage (0600X) - attributions spécifiques ARCEP
            '06000': 'Free Mobile',  # FRMO - Free Mobile
            '06001': 'Orange',  # FRTE - Orange
            '06002': 'SFR',  # SFR0 - SFR
            '06003': 'Bouygues Telecom',  # BOUY - Bouygues Telecom
            '06004': 'Free Mobile',  # Zeop Mobile et autres MVNO
            '06005': 'Orange',  # FRTE - Orange
            '06006': 'SFR',  # SFR0 - SFR
            '06007': 'Bouygues Telecom',  # BOUY - Bouygues Telecom
            '06008': 'Free Mobile',  # FRMO - Free Mobile
            '06009': 'Orange',  # FRTE - Orange
            
            # Préfixes 06XX principaux (basés sur les attributions historiques)
            # Orange (ex-France Télécom)
            '0601': 'Orange', '0602': 'Orange', '0603': 'Orange', '0604': 'Orange',
            '0605': 'Orange', '0606': 'Orange', '0607': 'Orange', '0608': 'Orange', '0609': 'Orange',
            '0610': 'Orange', '0611': 'Orange', '0612': 'Orange', '0613': 'Orange',
            '0614': 'Orange', '0615': 'Orange', '0616': 'Orange', '0617': 'Orange', '0618': 'Orange', '0619': 'Orange',
            '0620': 'Orange', '0621': 'Orange', '0622': 'Orange', '0623': 'Orange',
            '0624': 'Orange', '0625': 'Orange', '0626': 'Orange', '0627': 'Orange', '0628': 'Orange', '0629': 'Orange',
            '0630': 'Orange', '0631': 'Orange', '0632': 'Orange', '0633': 'Orange',
            '0634': 'Orange', '0635': 'Orange', '0636': 'Orange', '0637': 'Orange', '0638': 'Orange', '0639': 'Orange',
            
            # SFR
            '0640': 'SFR', '0641': 'SFR', '0642': 'SFR', '0643': 'SFR',
            '0644': 'SFR', '0645': 'SFR', '0646': 'SFR', '0647': 'SFR', '0648': 'SFR', '0649': 'SFR',
            '0650': 'SFR', '0651': 'SFR', '0652': 'SFR', '0653': 'SFR',
            '0654': 'SFR', '0655': 'SFR', '0656': 'SFR', '0657': 'SFR', '0658': 'SFR', '0659': 'SFR',
            '0660': 'SFR', '0661': 'SFR', '0662': 'SFR', '0663': 'SFR',
            '0664': 'SFR', '0665': 'SFR', '0666': 'SFR', '0667': 'SFR', '0668': 'SFR', '0669': 'SFR',
            '0670': 'SFR', '0671': 'SFR', '0672': 'SFR', '0673': 'SFR',
            '0674': 'SFR', '0675': 'SFR', '0676': 'SFR', '0677': 'SFR', '0678': 'SFR', '0679': 'SFR',
            
            # Bouygues Telecom
            '0680': 'Bouygues Telecom', '0681': 'Bouygues Telecom', '0682': 'Bouygues Telecom', '0683': 'Bouygues Telecom',
            '0684': 'Bouygues Telecom', '0685': 'Bouygues Telecom', '0686': 'Bouygues Telecom', '0687': 'Bouygues Telecom',
            '0688': 'Bouygues Telecom', '0689': 'Bouygues Telecom',
            '0690': 'Bouygues Telecom', '0691': 'Bouygues Telecom', '0692': 'Bouygues Telecom', '0693': 'Bouygues Telecom',
            '0694': 'Bouygues Telecom', '0695': 'Bouygues Telecom', '0696': 'Bouygues Telecom', '0697': 'Bouygues Telecom',
            '0698': 'Bouygues Telecom', '0699': 'Bouygues Telecom',
            
            # Free Mobile (souvent 079X)
            '0790': 'Free Mobile', '0791': 'Free Mobile', '0792': 'Free Mobile', '0793': 'Free Mobile',
            '0794': 'Free Mobile', '0795': 'Free Mobile', '0796': 'Free Mobile', '0797': 'Free Mobile',
            '0798': 'Free Mobile', '0799': 'Free Mobile',
            
            # Préfixes 07XX (portabilité totale, mais attributions initiales)
            '0700': 'Orange',  # Souvent Orange
            '0701': 'Orange', '0702': 'Orange', '0703': 'Orange',
            '0704': 'SFR', '0705': 'SFR', '0706': 'SFR', '0707': 'SFR',
            '0708': 'Bouygues Telecom', '0709': 'Bouygues Telecom',
            '0710': 'Orange', '0711': 'Orange', '0712': 'Orange', '0713': 'Orange',
            '0714': 'SFR', '0715': 'SFR', '0716': 'SFR', '0717': 'SFR',
            '0718': 'Bouygues Telecom', '0719': 'Bouygues Telecom',
            '0720': 'Orange', '0721': 'Orange', '0722': 'Orange', '0723': 'Orange',
            '0724': 'SFR', '0725': 'SFR', '0726': 'SFR', '0727': 'SFR',
            '0728': 'Bouygues Telecom', '0729': 'Bouygues Telecom',
            '0730': 'Orange', '0731': 'Orange', '0732': 'Orange', '0733': 'Orange',
            '0734': 'SFR', '0735': 'SFR', '0736': 'SFR', '0737': 'SFR',
            '0738': 'Bouygues Telecom', '0739': 'Bouygues Telecom',
            '0740': 'Orange', '0741': 'Orange', '0742': 'Orange', '0743': 'Orange',
            '0744': 'SFR', '0745': 'SFR', '0746': 'SFR', '0747': 'SFR',
            '0748': 'Bouygues Telecom', '0749': 'Bouygues Telecom',
            '0750': 'Orange', '0751': 'Orange', '0752': 'Orange', '0753': 'Orange',
            '0754': 'SFR', '0755': 'SFR', '0756': 'SFR', '0757': 'SFR',
            '0758': 'Bouygues Telecom', '0759': 'Bouygues Telecom',
            '0760': 'Orange', '0761': 'Orange', '0762': 'Orange', '0763': 'Orange',
            '0764': 'SFR', '0765': 'SFR', '0766': 'SFR', '0767': 'SFR',
            '0768': 'Bouygues Telecom', '0769': 'Bouygues Telecom',
            '0770': 'Orange', '0771': 'Orange', '0772': 'Orange', '0773': 'Orange',
            '0774': 'SFR', '0775': 'SFR', '0776': 'SFR', '0777': 'SFR',
            '0778': 'Bouygues Telecom', '0779': 'Bouygues Telecom',
            '0780': 'Orange', '0781': 'Orange', '0782': 'Orange', '0783': 'Orange',
            '0784': 'SFR', '0785': 'SFR', '0786': 'SFR', '0787': 'SFR',
            '0788': 'Bouygues Telecom', '0789': 'Bouygues Telecom',
        }
        
        # Préfixes mobiles par opérateur (pour compatibilité)
        self.operator_prefixes = {
            'Orange': {
                'mobile': ['06', '07'],
                'landline_prefixes': ['01', '02', '03', '04', '05'],
                'description': 'Orange (ex-France Télécom)'
            },
            'SFR': {
                'mobile': ['06', '07'],
                'landline_prefixes': ['01', '02', '03', '04', '05'],
                'description': 'SFR'
            },
            'Bouygues Telecom': {
                'mobile': ['06', '07'],
                'landline_prefixes': ['01', '02', '03', '04', '05'],
                'description': 'Bouygues Telecom'
            },
            'Free Mobile': {
                'mobile': ['06', '07'],
                'landline_prefixes': [],
                'description': 'Free Mobile'
            },
        }
        
        # Mapping plus précis basé sur les indicatifs régionaux historiques
        # 03 = Nord-Est (Lorraine, Alsace) - souvent SFR/Orange
        # Les numéros fixes 03XX sont souvent Orange ou SFR
        self.region_operator_hints = {
            '03': ['SFR', 'Orange'],  # Nord-Est souvent SFR/Orange (Lorraine, Alsace)
            '01': ['Orange', 'SFR'],  # Paris souvent Orange/SFR
            '04': ['Orange', 'SFR'],  # Sud-Est
            '05': ['Orange', 'SFR'],  # Sud-Ouest
            '02': ['Orange', 'SFR'],  # Nord-Ouest
        }
        
        # Mapping spécifique par préfixe de ville pour plus de précision
        # Metz (0387) est historiquement SFR
        self.city_operator_mapping = {
            '0387': 'SFR',  # Metz - SFR
            '0383': 'Orange',  # Nancy - souvent Orange
            '0388': 'Orange',  # Strasbourg - souvent Orange
            '0389': 'SFR',  # Mulhouse - souvent SFR
        }
    
    def _init_city_mapping(self):
        """
        Initialise le mapping des villes par indicatif
        """
        # Mapping indicatif -> ville principale (plus détaillé)
        self.city_by_prefix = {
            # 03 = Nord-Est
            '0387': 'Metz',  # 03 87 = Metz (Moselle)
            '0388': 'Strasbourg',  # 03 88 = Strasbourg (Bas-Rhin)
            '0389': 'Mulhouse',  # 03 89 = Mulhouse (Haut-Rhin)
            '0383': 'Nancy',  # 03 83 = Nancy (Meurthe-et-Moselle)
            '0390': 'Colmar',  # 03 90 = Colmar (Haut-Rhin)
            '0382': 'Épinal',  # 03 82 = Épinal (Vosges)
            '0384': 'Vesoul',  # 03 84 = Vesoul (Haute-Saône)
            '0385': 'Dijon',  # 03 85 = Dijon (Côte-d'Or)
            '0380': 'Belfort',  # 03 80 = Belfort (Territoire de Belfort)
            '0381': 'Besançon',  # 03 81 = Besançon (Doubs)
            # 01 = Île-de-France
            '0120': 'Paris',  # 01 20 = Paris
            '0142': 'Paris',  # 01 42 = Paris
            '0146': 'Paris',  # 01 46 = Paris
            '0143': 'Paris',  # 01 43 = Paris
            '0144': 'Paris',  # 01 44 = Paris
            '0145': 'Paris',  # 01 45 = Paris
            '0147': 'Paris',  # 01 47 = Paris
            '0148': 'Paris',  # 01 48 = Paris
            '0149': 'Paris',  # 01 49 = Paris
            '0160': 'Créteil',  # 01 60 = Créteil
            '0164': 'Versailles',  # 01 64 = Versailles
            '0140': 'Nanterre',  # 01 40 = Nanterre
            # 04 = Sud-Est
            '0472': 'Lyon',  # 04 72 = Lyon
            '0476': 'Grenoble',  # 04 76 = Grenoble
            '0477': 'Saint-Étienne',  # 04 77 = Saint-Étienne
            '0473': 'Clermont-Ferrand',  # 04 73 = Clermont-Ferrand
            '0488': 'Strasbourg',  # 04 88 = Strasbourg (ancien)
            # 05 = Sud-Ouest
            '0556': 'Bordeaux',  # 05 56 = Bordeaux
            '0561': 'Toulouse',  # 05 61 = Toulouse
            '0555': 'Limoges',  # 05 55 = Limoges
            '0559': 'Pau',  # 05 59 = Pau
            '0557': 'Bayonne',  # 05 57 = Bayonne
            '0467': 'Montpellier',  # 04 67 = Montpellier
            '0468': 'Perpignan',  # 04 68 = Perpignan
            '0466': 'Nîmes',  # 04 66 = Nîmes
        }
    
    def detect(self, phone_number: str) -> Dict[str, any]:
        """
        Détecte l'opérateur, la ville et la région pour un numéro français
        
        Args:
            phone_number: Numéro de téléphone (format +33... ou 0...)
            
        Returns:
            Dictionnaire avec les informations détectées
        """
        result = {
            'operator': None,
            'operator_description': None,
            'operator_full_name': None,
            'operator_type': None,
            'operator_website': None,
            'region': None,
            'city': None,
            'department': None,
            'postal_code': None,
            'line_type': None,
            'indicatif': None,
            'confidence': 0.0,
        }
        
        # Nettoyer et normaliser le numéro
        clean_number = self._clean_number(phone_number)
        
        # Vérifier si c'est un numéro français
        if not clean_number.startswith('+33'):
            return result
        
        # Extraire l'indicatif depuis le numéro original (pour préserver l'indicatif 0X)
        # Si le numéro original commence par 0, on peut extraire l'indicatif directement
        original_cleaned = re.sub(r'[^\d]', '', phone_number)
        if original_cleaned.startswith('0') and len(original_cleaned) >= 3:
            # Numéro au format national: 0X...
            indicatif = original_cleaned[:2]  # Ex: 03, 01, 06, etc.
            digits_after_indicatif = original_cleaned[2:]  # Ex: 55192515 pour 0355192515
        else:
            # Numéro déjà au format international: +33...
            # On doit deviner l'indicatif (peu fiable)
            digits = clean_number.replace('+33', '')
            if len(digits) < 1:
                return result
            # Pour les numéros français, le premier chiffre après +33 correspond à l'indicatif
            # Mais on ne peut pas savoir si c'était 01, 02, 03, etc.
            # On essaie de deviner basé sur la longueur et les patterns
            first_digit = digits[0]
            # Mapping approximatif (peu fiable)
            indicatif_map = {'1': '01', '2': '02', '3': '03', '4': '04', '5': '05', '6': '06', '7': '07'}
            indicatif = indicatif_map.get(first_digit, '0' + first_digit)
            digits_after_indicatif = digits[1:] if len(digits) > 1 else ''
        
        result['indicatif'] = indicatif
        
        logger.debug(f"Numéro original: {phone_number}, nettoyé: {clean_number}, indicatif: {indicatif}, digits_after: {digits_after_indicatif}")
        
        # Essayer d'abord avec la base de données (plus précise et complète)
        prefix_4 = None
        if len(digits_after_indicatif) >= 2:
            # Pour 0355192515: indicatif=03, digits_after=55192515, prefix_4=03+55=0355
            prefix_4 = indicatif + digits_after_indicatif[:2]  # Ex: 0355 pour 0355192515
            logger.debug(f"Recherche du préfixe {prefix_4} dans la base de données et les fichiers JSON")
            
            prefix_info = None
            # Essayer d'abord la base de données
            try:
                prefix_info = self.db_manager.get_prefix_info(prefix_4)
                if prefix_info:
                    logger.debug(f"Préfixe {prefix_4} trouvé dans la base de données")
            except Exception as e:
                logger.debug(f"Erreur lors de la recherche en DB: {e}")
            
            # Si pas dans la DB, essayer avec les données JSON
            if not prefix_info:
                prefix_info = self.data_manager.get_prefix_info(prefix_4)
                if prefix_info:
                    logger.debug(f"Préfixe {prefix_4} trouvé dans les fichiers JSON")
            
            if prefix_info:
                # Utiliser les données de référence
                result['city'] = prefix_info.get('city')
                result['region'] = prefix_info.get('region')
                result['operator'] = prefix_info.get('operator')
                result['line_type'] = 'landline' if indicatif in ['01', '02', '03', '04', '05'] else 'mobile' if indicatif in ['06', '07'] else 'special'
                result['confidence'] = 0.9  # Haute confiance avec données de référence
                
                # Ajouter des informations supplémentaires
                result['department'] = prefix_info.get('department')
                result['postal_code'] = prefix_info.get('postal_code')
                
                # Enrichir avec les infos opérateur
                if result['operator']:
                    operator_info = self.data_manager.get_operator_info(result['operator'])
                    if operator_info:
                        result['operator_description'] = operator_info.get('description')
                        result['operator_full_name'] = operator_info.get('full_name')
                        result['operator_type'] = operator_info.get('type')
                        result['operator_website'] = operator_info.get('website')
                
                # Enrichir avec les infos ville
                if result['city']:
                    city_info = self.data_manager.get_city_info(result['city'])
                    if city_info:
                        result['city_region'] = city_info.get('region')
                        result['city_department'] = city_info.get('department')
                        result['city_postal_code'] = city_info.get('postal_code')
                
                logger.info(f"Données de référence trouvées pour {prefix_4}: {result['city']}, {result['operator']}, {result['region']}")
                return result
            else:
                logger.debug(f"Préfixe {prefix_4} non trouvé dans les données de référence, utilisation de la détection basique")
        
        logger.debug(f"Détection française: indicatif={indicatif}, digits_after={digits_after_indicatif}, prefix_4={prefix_4 if prefix_4 else 'N/A'}")
        
        # Détecter le type de ligne et les informations de base
        if indicatif in ['06', '07']:
            result['line_type'] = 'mobile'
            result['operator'] = self._detect_mobile_operator(indicatif, digits_after_indicatif)
            result['confidence'] = 0.3  # Faible car portabilité
            
            # Pour les mobiles, on ne peut pas donner de région/ville précise (portabilité)
            # Mais on peut indiquer que c'est un mobile français
            result['country'] = 'France'
            result['region'] = 'France entière (mobile)'  # Indication générale
            
            # Enrichir avec les infos opérateur si trouvé
            if result['operator']:
                operator_info = self.data_manager.get_operator_info(result['operator'])
                if operator_info:
                    result['operator_description'] = operator_info.get('description')
                    result['operator_full_name'] = operator_info.get('full_name')
                    result['operator_type'] = operator_info.get('type')
                    result['operator_website'] = operator_info.get('website')
            
            logger.info(f"Ligne mobile détectée: indicatif={indicatif}, opérateur={result['operator']}")
        elif indicatif in ['01', '02', '03', '04', '05']:
            result['line_type'] = 'landline'
            result['operator'] = self._detect_landline_operator(indicatif, digits_after_indicatif)
            result['region'] = self._detect_region(indicatif)
            result['city'] = self._detect_city(indicatif, digits_after_indicatif)
            result['confidence'] = 0.5  # Confiance moyenne si préfixe exact non trouvé
            
            # Si on n'a pas trouvé de ville mais qu'on a une région, on peut au moins donner la région
            if not result['city'] and result['region']:
                logger.info(f"Ville non trouvée pour préfixe {prefix_4 if prefix_4 else 'N/A'}, mais région détectée: {result['region']}")
        elif indicatif in ['08', '09']:
            result['line_type'] = 'special'
            result['confidence'] = 0.5
        else:
            result['line_type'] = 'unknown'
            result['confidence'] = 0.1
        
        # Ajouter la description de l'opérateur
        if result['operator']:
            for op_name, op_data in self.operator_prefixes.items():
                if op_name == result['operator']:
                    result['operator_description'] = op_data['description']
                    break
        
        return result
    
    def _clean_number(self, phone_number: str) -> str:
        """
        Nettoie et normalise un numéro de téléphone
        
        Args:
            phone_number: Numéro à nettoyer
            
        Returns:
            Numéro nettoyé au format +33...
            
        Exemples:
            - 0355192515 -> +3355192515 (préserve l'indicatif 03)
            - 0387780916 -> +3387780916 (préserve l'indicatif 03)
            - +3355192515 -> +3355192515 (déjà au bon format)
        """
        # Retirer tous les caractères non numériques sauf +
        cleaned = re.sub(r'[^\d+]', '', phone_number)
        
        # Convertir 0 en +33 (préserve l'indicatif)
        # Ex: 0355192515 -> +3355192515 (le 03 devient partie du numéro après +33)
        if cleaned.startswith('0') and not cleaned.startswith('+33'):
            cleaned = '+33' + cleaned[1:]  # Enlève le 0, ajoute +33
        elif not cleaned.startswith('+'):
            cleaned = '+' + cleaned
        
        return cleaned
    
    def _detect_mobile_operator(self, indicatif: str, digits: str) -> Optional[str]:
        """
        Détecte l'opérateur mobile basé sur les préfixes attribués par l'ARCEP
        
        Args:
            indicatif: Indicatif (06 ou 07)
            digits: Chiffres après l'indicatif (ex: pour 0612345678 -> digits=12345678)
            
        Returns:
            Nom de l'opérateur ou None
            
        Note: La portabilité des numéros rend cette détection approximative.
        Les résultats sont basés sur les préfixes historiques d'attribution par l'ARCEP.
        Source: https://fr.wikipedia.org/wiki/Liste_des_préfixes_des_opérateurs_de_téléphonie_mobile_en_France
        """
        if len(digits) < 1:
            return None
        
        # Construire le préfixe complet (indicatif + 4 premiers chiffres = ABPQ)
        # Ex: 0612345678 -> indicatif=06, digits=12345678 -> prefix=0612
        # Ex: 0798765432 -> indicatif=07, digits=98765432 -> prefix=0798
        
        # Essayer d'abord avec 4 chiffres (préfixe ABPQ complet)
        if len(digits) >= 4:
            prefix_4 = indicatif + digits[:4]
            if prefix_4 in self.mobile_prefixes:
                operator = self.mobile_prefixes[prefix_4]
                logger.debug(f"Opérateur mobile détecté via préfixe 4 chiffres {prefix_4}: {operator}")
                return operator
        
        # Essayer avec 3 chiffres (préfixe ABP)
        if len(digits) >= 3:
            prefix_3 = indicatif + digits[:3]
            # Chercher les préfixes qui commencent par ce pattern
            matching_prefixes = {k: v for k, v in self.mobile_prefixes.items() if k.startswith(prefix_3)}
            if matching_prefixes:
                # Prendre le premier match (le plus spécifique)
                operator = list(matching_prefixes.values())[0]
                logger.debug(f"Opérateur mobile détecté via préfixe 3 chiffres {prefix_3}: {operator}")
                return operator
        
        # Essayer avec 2 chiffres (préfixe AB)
        if len(digits) >= 2:
            prefix_2 = indicatif + digits[:2]
            # Chercher les préfixes qui commencent par ce pattern
            matching_prefixes = {k: v for k, v in self.mobile_prefixes.items() if k.startswith(prefix_2)}
            if matching_prefixes:
                # Prendre le premier match (le plus spécifique)
                operator = list(matching_prefixes.values())[0]
                logger.debug(f"Opérateur mobile détecté via préfixe 2 chiffres {prefix_2}: {operator}")
                return operator
        
        # Fallback: utiliser le premier chiffre (moins précis)
        first_digit = digits[0]
        if indicatif == '06':
            if first_digit in ['0', '1', '2', '3']:
                return 'Orange'  # Historiquement Orange
            elif first_digit in ['4', '5', '6', '7']:
                return 'SFR'  # Historiquement SFR
            elif first_digit in ['8', '9']:
                return 'Bouygues Telecom'  # Historiquement Bouygues
        elif indicatif == '07':
            # Pour 07, la portabilité est totale depuis 2007
            if first_digit in ['0', '1', '2', '3']:
                return 'Orange'  # Probablement Orange
            elif first_digit in ['4', '5', '6', '7']:
                return 'SFR'  # Probablement SFR
            elif first_digit == '8':
                return 'Bouygues Telecom'  # Probablement Bouygues
            elif first_digit == '9':
                return 'Free Mobile'  # Souvent Free Mobile (depuis 2012)
        
        return None
    
    def _detect_landline_operator(self, indicatif: str, digits: str) -> Optional[str]:
        """
        Détecte l'opérateur pour une ligne fixe
        
        Args:
            indicatif: Indicatif régional (01-05)
            digits: Tous les chiffres après +33
            
        Returns:
            Nom de l'opérateur ou None
        """
        # Vérifier d'abord le mapping spécifique par ville (plus précis)
        if len(digits) >= 4:
            prefix_4 = indicatif + digits[2:4]  # Ex: 0387 pour Metz
            if prefix_4 in self.city_operator_mapping:
                return self.city_operator_mapping[prefix_4]
        
        # Utiliser les hints régionaux si pas de mapping spécifique
        if indicatif in self.region_operator_hints:
            operators = self.region_operator_hints[indicatif]
            # Retourner le premier opérateur de la liste
            return operators[0] if operators else None
        
        return None
    
    def _detect_region(self, indicatif: str) -> Optional[str]:
        """
        Détecte la région basée sur l'indicatif
        
        Args:
            indicatif: Indicatif régional (01-05)
            
        Returns:
            Nom de la région ou None
        """
        if indicatif in self.region_mapping:
            return self.region_mapping[indicatif]['region']
        return None
    
    def _detect_city(self, indicatif: str, digits: str) -> Optional[str]:
        """
        Détecte la ville basée sur l'indicatif et les préfixes
        
        Args:
            indicatif: Indicatif régional (ex: 03)
            digits: Tous les chiffres après +33 (ex: 87780916 pour 0387780916)
            
        Returns:
            Nom de la ville ou None
        """
        # Vérifier le mapping direct par préfixe 4 chiffres
        # Ex: pour 0387780916 -> indicatif=03, digits=87780916 -> prefix_4=0387
        # Ex: pour 0355192515 -> indicatif=03, digits=55192515 -> prefix_4=0355
        if len(digits) >= 2:
            prefix_4 = indicatif + digits[:2]  # Ex: 03 + 55 = 0355, 03 + 87 = 0387
            if prefix_4 in self.city_by_prefix:
                return self.city_by_prefix[prefix_4]
        
        # Vérifier dans le mapping régional avec les sous-préfixes
        if indicatif in self.region_mapping:
            cities = self.region_mapping[indicatif]['cities']
            # Essayer de deviner la ville basée sur les 2 premiers chiffres après l'indicatif
            if len(digits) >= 2:
                sub_prefix = digits[0:2]  # Ex: 87 pour Metz (0387)
                # Mapping approximatif pour le Nord-Est (03)
                city_hints = {
                    '87': 'Metz',  # 03 87 = Metz
                    '83': 'Nancy',  # 03 83 = Nancy
                    '88': 'Strasbourg',  # 03 88 = Strasbourg
                    '89': 'Mulhouse',  # 03 89 = Mulhouse
                    '90': 'Colmar',  # 03 90 = Colmar
                    '82': 'Épinal',  # 03 82 = Épinal
                    '84': 'Vesoul',  # 03 84 = Vesoul
                    '85': 'Dijon',  # 03 85 = Dijon
                    '80': 'Belfort',  # 03 80 = Belfort
                    '81': 'Besançon',  # 03 81 = Besançon
                }
                if sub_prefix in city_hints and indicatif == '03':
                    return city_hints[sub_prefix]
            
            # Par défaut, retourner la première ville de la région
            return cities[0] if cities else None
        
        return None
    
    def get_detailed_info(self, phone_number: str) -> Dict[str, any]:
        """
        Obtient des informations détaillées sur un numéro français
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Dictionnaire avec toutes les informations
        """
        detection = self.detect(phone_number)
        
        result = {
            'phone_number': phone_number,
            'normalized_number': self._clean_number(phone_number),
            **detection
        }
        
        # Ajouter des informations supplémentaires si disponible
        if detection['indicatif'] in self.region_mapping:
            region_info = self.region_mapping[detection['indicatif']]
            result['region_description'] = region_info.get('description')
            result['possible_cities'] = region_info.get('cities', [])
        
        return result

