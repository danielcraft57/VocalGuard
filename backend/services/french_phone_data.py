"""
Gestionnaire de données de référence pour les numéros français
Télécharge et utilise des fichiers de référence pour enrichir les informations
"""

import json
import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from loguru import logger
import httpx


class FrenchPhoneDataManager:
    """
    Gère les données de référence pour les numéros français
    """
    
    def __init__(self, data_path: Path):
        """
        Initialise le gestionnaire de données
        
        Args:
            data_path: Chemin vers le dossier de données
        """
        self.data_path = data_path
        self.data_path.mkdir(parents=True, exist_ok=True)
        
        # Fichiers de référence
        self.prefix_file = self.data_path / "french_prefixes.json"
        self.operator_file = self.data_path / "french_operators.json"
        self.city_file = self.data_path / "french_cities.json"
        
        # Données en mémoire
        self.prefix_data: Dict[str, Dict] = {}
        self.operator_data: Dict[str, Dict] = {}
        self.city_data: Dict[str, Dict] = {}
        
        # Charger les données
        self._load_data()
    
    def _load_data(self):
        """Charge les données depuis les fichiers"""
        # Charger les préfixes
        if self.prefix_file.exists():
            try:
                with open(self.prefix_file, 'r', encoding='utf-8') as f:
                    self.prefix_data = json.load(f)
                logger.info(f"Chargé {len(self.prefix_data)} préfixes français")
            except Exception as e:
                logger.warning(f"Erreur lors du chargement des préfixes: {e}")
        
        # Charger les opérateurs
        if self.operator_file.exists():
            try:
                with open(self.operator_file, 'r', encoding='utf-8') as f:
                    self.operator_data = json.load(f)
                logger.info(f"Chargé {len(self.operator_data)} opérateurs")
            except Exception as e:
                logger.warning(f"Erreur lors du chargement des opérateurs: {e}")
        
        # Charger les villes
        if self.city_file.exists():
            try:
                with open(self.city_file, 'r', encoding='utf-8') as f:
                    self.city_data = json.load(f)
                logger.info(f"Chargé {len(self.city_data)} villes")
            except Exception as e:
                logger.warning(f"Erreur lors du chargement des villes: {e}")
        
        # Toujours initialiser avec les données de base si pas de fichier
        # Cela garantit qu'on a au moins les données de base
        if not self.prefix_file.exists() or not self.prefix_data:
            logger.info("Initialisation des données par défaut pour les numéros français")
            self._init_default_data()
            self._save_data()
    
    def _init_default_data(self):
        """Initialise les données par défaut avec un mapping complet"""
        logger.info("Initialisation des données par défaut pour les numéros français")
        
        # Mapping complet des préfixes français (indicatif + 2 chiffres)
        self.prefix_data = {
            # 03 = Nord-Est / Lorraine / Alsace
            '0387': {'city': 'Metz', 'region': 'Grand Est', 'department': 'Moselle', 'operator': 'SFR', 'postal_code': '57000'},
            '0383': {'city': 'Nancy', 'region': 'Grand Est', 'department': 'Meurthe-et-Moselle', 'operator': 'Orange', 'postal_code': '54000'},
            '0388': {'city': 'Strasbourg', 'region': 'Grand Est', 'department': 'Bas-Rhin', 'operator': 'Orange', 'postal_code': '67000'},
            '0389': {'city': 'Mulhouse', 'region': 'Grand Est', 'department': 'Haut-Rhin', 'operator': 'SFR', 'postal_code': '68100'},
            '0390': {'city': 'Colmar', 'region': 'Grand Est', 'department': 'Haut-Rhin', 'operator': 'Orange', 'postal_code': '68000'},
            '0382': {'city': 'Épinal', 'region': 'Grand Est', 'department': 'Vosges', 'operator': 'Orange', 'postal_code': '88000'},
            '0384': {'city': 'Vesoul', 'region': 'Bourgogne-Franche-Comté', 'department': 'Haute-Saône', 'operator': 'Orange', 'postal_code': '70000'},
            '0385': {'city': 'Dijon', 'region': 'Bourgogne-Franche-Comté', 'department': 'Côte-d\'Or', 'operator': 'Orange', 'postal_code': '21000'},
            '0380': {'city': 'Belfort', 'region': 'Bourgogne-Franche-Comté', 'department': 'Territoire de Belfort', 'operator': 'Orange', 'postal_code': '90000'},
            '0381': {'city': 'Besançon', 'region': 'Bourgogne-Franche-Comté', 'department': 'Doubs', 'operator': 'Orange', 'postal_code': '25000'},
            '0386': {'city': 'Châlons-en-Champagne', 'region': 'Grand Est', 'department': 'Marne', 'operator': 'Orange', 'postal_code': '51000'},
            '0326': {'city': 'Reims', 'region': 'Grand Est', 'department': 'Marne', 'operator': 'Orange', 'postal_code': '51100'},
            '0327': {'city': 'Troyes', 'region': 'Grand Est', 'department': 'Aube', 'operator': 'Orange', 'postal_code': '10000'},
            '0328': {'city': 'Arras', 'region': 'Hauts-de-France', 'department': 'Pas-de-Calais', 'operator': 'Orange', 'postal_code': '62000'},
            '0329': {'city': 'Bar-le-Duc', 'region': 'Grand Est', 'department': 'Meuse', 'operator': 'Orange', 'postal_code': '55000'},
            '0325': {'city': 'Verdun', 'region': 'Grand Est', 'department': 'Meuse', 'operator': 'Orange', 'postal_code': '55100'},
            '0320': {'city': 'Lille', 'region': 'Hauts-de-France', 'department': 'Nord', 'operator': 'Orange', 'postal_code': '59000'},
            '0321': {'city': 'Lille', 'region': 'Hauts-de-France', 'department': 'Nord', 'operator': 'Orange', 'postal_code': '59000'},
            '0322': {'city': 'Amiens', 'region': 'Hauts-de-France', 'department': 'Somme', 'operator': 'Orange', 'postal_code': '80000'},
            '0323': {'city': 'Amiens', 'region': 'Hauts-de-France', 'department': 'Somme', 'operator': 'Orange', 'postal_code': '80000'},
            '0324': {'city': 'Laon', 'region': 'Hauts-de-France', 'department': 'Aisne', 'operator': 'Orange', 'postal_code': '02000'},
            
            # 01 = Île-de-France
            '0142': {'city': 'Paris', 'region': 'Île-de-France', 'department': 'Paris', 'operator': 'Orange', 'postal_code': '75001'},
            '0143': {'city': 'Paris', 'region': 'Île-de-France', 'department': 'Paris', 'operator': 'Orange', 'postal_code': '75001'},
            '0144': {'city': 'Paris', 'region': 'Île-de-France', 'department': 'Paris', 'operator': 'Orange', 'postal_code': '75001'},
            '0145': {'city': 'Paris', 'region': 'Île-de-France', 'department': 'Paris', 'operator': 'Orange', 'postal_code': '75001'},
            '0146': {'city': 'Paris', 'region': 'Île-de-France', 'department': 'Paris', 'operator': 'Orange', 'postal_code': '75001'},
            '0147': {'city': 'Paris', 'region': 'Île-de-France', 'department': 'Paris', 'operator': 'Orange', 'postal_code': '75001'},
            '0148': {'city': 'Paris', 'region': 'Île-de-France', 'department': 'Paris', 'operator': 'Orange', 'postal_code': '75001'},
            '0149': {'city': 'Paris', 'region': 'Île-de-France', 'department': 'Paris', 'operator': 'Orange', 'postal_code': '75001'},
            '0140': {'city': 'Nanterre', 'region': 'Île-de-France', 'department': 'Hauts-de-Seine', 'operator': 'Orange', 'postal_code': '92000'},
            '0141': {'city': 'Créteil', 'region': 'Île-de-France', 'department': 'Val-de-Marne', 'operator': 'Orange', 'postal_code': '94000'},
            '0160': {'city': 'Créteil', 'region': 'Île-de-France', 'department': 'Val-de-Marne', 'operator': 'Orange', 'postal_code': '94000'},
            '0164': {'city': 'Versailles', 'region': 'Île-de-France', 'department': 'Yvelines', 'operator': 'Orange', 'postal_code': '78000'},
            '0130': {'city': 'Évry', 'region': 'Île-de-France', 'department': 'Essonne', 'operator': 'Orange', 'postal_code': '91000'},
            '0134': {'city': 'Bobigny', 'region': 'Île-de-France', 'department': 'Seine-Saint-Denis', 'operator': 'Orange', 'postal_code': '93000'},
            '0139': {'city': 'Nanterre', 'region': 'Île-de-France', 'department': 'Hauts-de-Seine', 'operator': 'Orange', 'postal_code': '92000'},
            '0138': {'city': 'Versailles', 'region': 'Île-de-France', 'department': 'Yvelines', 'operator': 'Orange', 'postal_code': '78000'},
            '0137': {'city': 'Créteil', 'region': 'Île-de-France', 'department': 'Val-de-Marne', 'operator': 'Orange', 'postal_code': '94000'},
            '0136': {'city': 'Meaux', 'region': 'Île-de-France', 'department': 'Seine-et-Marne', 'operator': 'Orange', 'postal_code': '77100'},
            '0135': {'city': 'Melun', 'region': 'Île-de-France', 'department': 'Seine-et-Marne', 'operator': 'Orange', 'postal_code': '77000'},
            '0133': {'city': 'Pontoise', 'region': 'Île-de-France', 'department': 'Val-d\'Oise', 'operator': 'Orange', 'postal_code': '95300'},
            '0132': {'city': 'Argenteuil', 'region': 'Île-de-France', 'department': 'Val-d\'Oise', 'operator': 'Orange', 'postal_code': '95100'},
            '0131': {'city': 'Cergy', 'region': 'Île-de-France', 'department': 'Val-d\'Oise', 'operator': 'Orange', 'postal_code': '95000'},
            '0169': {'city': 'Fontainebleau', 'region': 'Île-de-France', 'department': 'Seine-et-Marne', 'operator': 'Orange', 'postal_code': '77300'},
            '0168': {'city': 'Provins', 'region': 'Île-de-France', 'department': 'Seine-et-Marne', 'operator': 'Orange', 'postal_code': '77160'},
            '0167': {'city': 'Coulommiers', 'region': 'Île-de-France', 'department': 'Seine-et-Marne', 'operator': 'Orange', 'postal_code': '77120'},
            '0166': {'city': 'Montereau-Fault-Yonne', 'region': 'Île-de-France', 'department': 'Seine-et-Marne', 'operator': 'Orange', 'postal_code': '77130'},
            '0165': {'city': 'Nemours', 'region': 'Île-de-France', 'department': 'Seine-et-Marne', 'operator': 'Orange', 'postal_code': '77140'},
            '0163': {'city': 'Lagny-sur-Marne', 'region': 'Île-de-France', 'department': 'Seine-et-Marne', 'operator': 'Orange', 'postal_code': '77400'},
            '0162': {'city': 'Torcy', 'region': 'Île-de-France', 'department': 'Seine-et-Marne', 'operator': 'Orange', 'postal_code': '77200'},
            '0161': {'city': 'Chelles', 'region': 'Île-de-France', 'department': 'Seine-et-Marne', 'operator': 'Orange', 'postal_code': '77500'},
            
            # 02 = Nord-Ouest (Bretagne, Centre-Val de Loire, Normandie, Pays de la Loire) + Océan Indien
            # Normandie
            '0228': {'city': 'Caen', 'region': 'Normandie', 'department': 'Calvados', 'operator': 'Orange', 'postal_code': '14000'},
            '0231': {'city': 'Rouen', 'region': 'Normandie', 'department': 'Seine-Maritime', 'operator': 'Orange', 'postal_code': '76000'},
            '0232': {'city': 'Rouen', 'region': 'Normandie', 'department': 'Seine-Maritime', 'operator': 'Orange', 'postal_code': '76000'},
            '0233': {'city': 'Le Havre', 'region': 'Normandie', 'department': 'Seine-Maritime', 'operator': 'Orange', 'postal_code': '76600'},
            '0235': {'city': 'Cherbourg-en-Cotentin', 'region': 'Normandie', 'department': 'Manche', 'operator': 'Orange', 'postal_code': '50100'},
            '0234': {'city': 'Évreux', 'region': 'Normandie', 'department': 'Eure', 'operator': 'Orange', 'postal_code': '27000'},
            '0233': {'city': 'Alençon', 'region': 'Normandie', 'department': 'Orne', 'operator': 'Orange', 'postal_code': '61000'},
            # Pays de la Loire
            '0240': {'city': 'Nantes', 'region': 'Pays de la Loire', 'department': 'Loire-Atlantique', 'operator': 'Orange', 'postal_code': '44000'},
            '0241': {'city': 'Angers', 'region': 'Pays de la Loire', 'department': 'Maine-et-Loire', 'operator': 'Orange', 'postal_code': '49000'},
            '0243': {'city': 'Le Mans', 'region': 'Pays de la Loire', 'department': 'Sarthe', 'operator': 'Orange', 'postal_code': '72000'},
            '0242': {'city': 'Saint-Nazaire', 'region': 'Pays de la Loire', 'department': 'Loire-Atlantique', 'operator': 'Orange', 'postal_code': '44600'},
            '0251': {'city': 'La Roche-sur-Yon', 'region': 'Pays de la Loire', 'department': 'Vendée', 'operator': 'Orange', 'postal_code': '85000'},
            '0243': {'city': 'Laval', 'region': 'Pays de la Loire', 'department': 'Mayenne', 'operator': 'Orange', 'postal_code': '53000'},
            '0241': {'city': 'Cholet', 'region': 'Pays de la Loire', 'department': 'Maine-et-Loire', 'operator': 'Orange', 'postal_code': '49300'},
            # Bretagne
            '0298': {'city': 'Brest', 'region': 'Bretagne', 'department': 'Finistère', 'operator': 'Orange', 'postal_code': '29200'},
            '0299': {'city': 'Rennes', 'region': 'Bretagne', 'department': 'Ille-et-Vilaine', 'operator': 'Orange', 'postal_code': '35000'},
            '0297': {'city': 'Lorient', 'region': 'Bretagne', 'department': 'Morbihan', 'operator': 'Orange', 'postal_code': '56100'},
            '0296': {'city': 'Vannes', 'region': 'Bretagne', 'department': 'Morbihan', 'operator': 'Orange', 'postal_code': '56000'},
            '0299': {'city': 'Saint-Malo', 'region': 'Bretagne', 'department': 'Ille-et-Vilaine', 'operator': 'Orange', 'postal_code': '35400'},
            '0298': {'city': 'Quimper', 'region': 'Bretagne', 'department': 'Finistère', 'operator': 'Orange', 'postal_code': '29000'},
            '0296': {'city': 'Saint-Brieuc', 'region': 'Bretagne', 'department': 'Côtes-d\'Armor', 'operator': 'Orange', 'postal_code': '22000'},
            # Centre-Val de Loire
            '0237': {'city': 'Tours', 'region': 'Centre-Val de Loire', 'department': 'Indre-et-Loire', 'operator': 'Orange', 'postal_code': '37000'},
            '0238': {'city': 'Orléans', 'region': 'Centre-Val de Loire', 'department': 'Loiret', 'operator': 'Orange', 'postal_code': '45000'},
            '0234': {'city': 'Blois', 'region': 'Centre-Val de Loire', 'department': 'Loir-et-Cher', 'operator': 'Orange', 'postal_code': '41000'},
            '0248': {'city': 'Bourges', 'region': 'Centre-Val de Loire', 'department': 'Cher', 'operator': 'Orange', 'postal_code': '18000'},
            '0254': {'city': 'Châteauroux', 'region': 'Centre-Val de Loire', 'department': 'Indre', 'operator': 'Orange', 'postal_code': '36000'},
            '0237': {'city': 'Chartres', 'region': 'Centre-Val de Loire', 'department': 'Eure-et-Loir', 'operator': 'Orange', 'postal_code': '28000'},
            
            # 04 = Sud-Est (Auvergne-Rhône-Alpes, Corse, Provence-Alpes-Côte d'Azur, Occitanie Languedoc-Roussillon)
            # Auvergne-Rhône-Alpes
            '0472': {'city': 'Lyon', 'region': 'Auvergne-Rhône-Alpes', 'department': 'Rhône', 'operator': 'Orange', 'postal_code': '69000'},
            '0476': {'city': 'Grenoble', 'region': 'Auvergne-Rhône-Alpes', 'department': 'Isère', 'operator': 'Orange', 'postal_code': '38000'},
            '0477': {'city': 'Saint-Étienne', 'region': 'Auvergne-Rhône-Alpes', 'department': 'Loire', 'operator': 'Orange', 'postal_code': '42000'},
            '0473': {'city': 'Clermont-Ferrand', 'region': 'Auvergne-Rhône-Alpes', 'department': 'Puy-de-Dôme', 'operator': 'Orange', 'postal_code': '63000'},
            '0482': {'city': 'Annecy', 'region': 'Auvergne-Rhône-Alpes', 'department': 'Haute-Savoie', 'operator': 'Orange', 'postal_code': '74000'},
            '0479': {'city': 'Chambéry', 'region': 'Auvergne-Rhône-Alpes', 'department': 'Savoie', 'operator': 'Orange', 'postal_code': '73000'},
            '0474': {'city': 'Roanne', 'region': 'Auvergne-Rhône-Alpes', 'department': 'Loire', 'operator': 'Orange', 'postal_code': '42300'},
            '0475': {'city': 'Valence', 'region': 'Auvergne-Rhône-Alpes', 'department': 'Drôme', 'operator': 'Orange', 'postal_code': '26000'},
            '0471': {'city': 'Le Puy-en-Velay', 'region': 'Auvergne-Rhône-Alpes', 'department': 'Haute-Loire', 'operator': 'Orange', 'postal_code': '43000'},
            '0470': {'city': 'Moulins', 'region': 'Auvergne-Rhône-Alpes', 'department': 'Allier', 'operator': 'Orange', 'postal_code': '03000'},
            '0478': {'city': 'Bourg-en-Bresse', 'region': 'Auvergne-Rhône-Alpes', 'department': 'Ain', 'operator': 'Orange', 'postal_code': '01000'},
            # Provence-Alpes-Côte d'Azur
            '0442': {'city': 'Marseille', 'region': 'Provence-Alpes-Côte d\'Azur', 'department': 'Bouches-du-Rhône', 'operator': 'Orange', 'postal_code': '13000'},
            '0449': {'city': 'Nice', 'region': 'Provence-Alpes-Côte d\'Azur', 'department': 'Alpes-Maritimes', 'operator': 'Orange', 'postal_code': '06000'},
            '0444': {'city': 'Aix-en-Provence', 'region': 'Provence-Alpes-Côte d\'Azur', 'department': 'Bouches-du-Rhône', 'operator': 'Orange', 'postal_code': '13100'},
            '0494': {'city': 'Toulon', 'region': 'Provence-Alpes-Côte d\'Azur', 'department': 'Var', 'operator': 'Orange', 'postal_code': '83000'},
            '0490': {'city': 'Avignon', 'region': 'Provence-Alpes-Côte d\'Azur', 'department': 'Vaucluse', 'operator': 'Orange', 'postal_code': '84000'},
            '0493': {'city': 'Cannes', 'region': 'Provence-Alpes-Côte d\'Azur', 'department': 'Alpes-Maritimes', 'operator': 'Orange', 'postal_code': '06400'},
            '0493': {'city': 'Antibes', 'region': 'Provence-Alpes-Côte d\'Azur', 'department': 'Alpes-Maritimes', 'operator': 'Orange', 'postal_code': '06600'},
            '0492': {'city': 'Gap', 'region': 'Provence-Alpes-Côte d\'Azur', 'department': 'Hautes-Alpes', 'operator': 'Orange', 'postal_code': '05000'},
            '0492': {'city': 'Digne-les-Bains', 'region': 'Provence-Alpes-Côte d\'Azur', 'department': 'Alpes-de-Haute-Provence', 'operator': 'Orange', 'postal_code': '04000'},
            # Occitanie (Languedoc-Roussillon)
            '0467': {'city': 'Montpellier', 'region': 'Occitanie', 'department': 'Hérault', 'operator': 'Orange', 'postal_code': '34000'},
            '0468': {'city': 'Perpignan', 'region': 'Occitanie', 'department': 'Pyrénées-Orientales', 'operator': 'Orange', 'postal_code': '66000'},
            '0466': {'city': 'Nîmes', 'region': 'Occitanie', 'department': 'Gard', 'operator': 'Orange', 'postal_code': '30000'},
            '0467': {'city': 'Béziers', 'region': 'Occitanie', 'department': 'Hérault', 'operator': 'Orange', 'postal_code': '34500'},
            '0468': {'city': 'Carcassonne', 'region': 'Occitanie', 'department': 'Aude', 'operator': 'Orange', 'postal_code': '11000'},
            '0467': {'city': 'Sète', 'region': 'Occitanie', 'department': 'Hérault', 'operator': 'Orange', 'postal_code': '34200'},
            '0468': {'city': 'Narbonne', 'region': 'Occitanie', 'department': 'Aude', 'operator': 'Orange', 'postal_code': '11100'},
            # Corse
            '0495': {'city': 'Ajaccio', 'region': 'Corse', 'department': 'Corse-du-Sud', 'operator': 'Orange', 'postal_code': '20000'},
            '0495': {'city': 'Bastia', 'region': 'Corse', 'department': 'Haute-Corse', 'operator': 'Orange', 'postal_code': '20200'},
            
            # 05 = Sud-Ouest (Nouvelle-Aquitaine, Occitanie Midi-Pyrénées) + DOM
            # Nouvelle-Aquitaine
            '0556': {'city': 'Bordeaux', 'region': 'Nouvelle-Aquitaine', 'department': 'Gironde', 'operator': 'Orange', 'postal_code': '33000'},
            '0555': {'city': 'Limoges', 'region': 'Nouvelle-Aquitaine', 'department': 'Haute-Vienne', 'operator': 'Orange', 'postal_code': '87000'},
            '0559': {'city': 'Pau', 'region': 'Nouvelle-Aquitaine', 'department': 'Pyrénées-Atlantiques', 'operator': 'Orange', 'postal_code': '64000'},
            '0557': {'city': 'Bayonne', 'region': 'Nouvelle-Aquitaine', 'department': 'Pyrénées-Atlantiques', 'operator': 'Orange', 'postal_code': '64100'},
            '0546': {'city': 'La Rochelle', 'region': 'Nouvelle-Aquitaine', 'department': 'Charente-Maritime', 'operator': 'Orange', 'postal_code': '17000'},
            '0549': {'city': 'Poitiers', 'region': 'Nouvelle-Aquitaine', 'department': 'Vienne', 'operator': 'Orange', 'postal_code': '86000'},
            '0553': {'city': 'Périgueux', 'region': 'Nouvelle-Aquitaine', 'department': 'Dordogne', 'operator': 'Orange', 'postal_code': '24000'},
            '0555': {'city': 'Brive-la-Gaillarde', 'region': 'Nouvelle-Aquitaine', 'department': 'Corrèze', 'operator': 'Orange', 'postal_code': '19100'},
            '0545': {'city': 'Angoulême', 'region': 'Nouvelle-Aquitaine', 'department': 'Charente', 'operator': 'Orange', 'postal_code': '16000'},
            '0553': {'city': 'Agen', 'region': 'Nouvelle-Aquitaine', 'department': 'Lot-et-Garonne', 'operator': 'Orange', 'postal_code': '47000'},
            '0549': {'city': 'Niort', 'region': 'Nouvelle-Aquitaine', 'department': 'Deux-Sèvres', 'operator': 'Orange', 'postal_code': '79000'},
            '0555': {'city': 'Guéret', 'region': 'Nouvelle-Aquitaine', 'department': 'Creuse', 'operator': 'Orange', 'postal_code': '23000'},
            # Occitanie (Midi-Pyrénées)
            '0561': {'city': 'Toulouse', 'region': 'Occitanie', 'department': 'Haute-Garonne', 'operator': 'Orange', 'postal_code': '31000'},
            '0562': {'city': 'Tarbes', 'region': 'Occitanie', 'department': 'Hautes-Pyrénées', 'operator': 'Orange', 'postal_code': '65000'},
            '0563': {'city': 'Albi', 'region': 'Occitanie', 'department': 'Tarn', 'operator': 'Orange', 'postal_code': '81000'},
            '0563': {'city': 'Montauban', 'region': 'Occitanie', 'department': 'Tarn-et-Garonne', 'operator': 'Orange', 'postal_code': '82000'},
            '0561': {'city': 'Foix', 'region': 'Occitanie', 'department': 'Ariège', 'operator': 'Orange', 'postal_code': '09000'},
            '0565': {'city': 'Cahors', 'region': 'Occitanie', 'department': 'Lot', 'operator': 'Orange', 'postal_code': '46000'},
            '0565': {'city': 'Rodez', 'region': 'Occitanie', 'department': 'Aveyron', 'operator': 'Orange', 'postal_code': '12000'},
            '0562': {'city': 'Auch', 'region': 'Occitanie', 'department': 'Gers', 'operator': 'Orange', 'postal_code': '32000'},
            # DOM (Guadeloupe, Martinique, Guyane)
            '0590': {'city': 'Pointe-à-Pitre', 'region': 'Guadeloupe', 'department': 'Guadeloupe', 'operator': 'Orange', 'postal_code': '97100'},
            '0596': {'city': 'Fort-de-France', 'region': 'Martinique', 'department': 'Martinique', 'operator': 'Orange', 'postal_code': '97200'},
            '0594': {'city': 'Cayenne', 'region': 'Guyane', 'department': 'Guyane', 'operator': 'Orange', 'postal_code': '97300'},
        }
        
        # Données sur les opérateurs
        self.operator_data = {
            'Orange': {
                'name': 'Orange',
                'full_name': 'Orange France',
                'type': 'opérateur historique',
                'description': 'Orange (ex-France Télécom)',
                'website': 'https://www.orange.fr',
                'color': '#FF6600'
            },
            'SFR': {
                'name': 'SFR',
                'full_name': 'SFR',
                'type': 'opérateur alternatif',
                'description': 'SFR',
                'website': 'https://www.sfr.fr',
                'color': '#E20074'
            },
            'Bouygues Telecom': {
                'name': 'Bouygues Telecom',
                'full_name': 'Bouygues Telecom',
                'type': 'opérateur alternatif',
                'description': 'Bouygues Telecom',
                'website': 'https://www.bouyguestelecom.fr',
                'color': '#FED100'
            },
            'Free Mobile': {
                'name': 'Free Mobile',
                'full_name': 'Free Mobile',
                'type': 'opérateur alternatif',
                'description': 'Free Mobile',
                'website': 'https://mobile.free.fr',
                'color': '#00A0E3'
            },
        }
        
        # Données sur les villes (enrichies)
        self.city_data = {}
        for prefix, info in self.prefix_data.items():
            city = info.get('city')
            if city and city not in self.city_data:
                self.city_data[city] = {
                    'name': city,
                    'region': info.get('region'),
                    'department': info.get('department'),
                    'postal_code': info.get('postal_code'),
                    'prefixes': []
                }
            if city and city in self.city_data:
                self.city_data[city]['prefixes'].append(prefix)
    
    def _save_data(self):
        """Sauvegarde les données dans les fichiers"""
        try:
            with open(self.prefix_file, 'w', encoding='utf-8') as f:
                json.dump(self.prefix_data, f, ensure_ascii=False, indent=2)
            with open(self.operator_file, 'w', encoding='utf-8') as f:
                json.dump(self.operator_data, f, ensure_ascii=False, indent=2)
            with open(self.city_file, 'w', encoding='utf-8') as f:
                json.dump(self.city_data, f, ensure_ascii=False, indent=2)
            logger.info("Données sauvegardées")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde: {e}")
    
    def get_prefix_info(self, prefix: str) -> Optional[Dict]:
        """
        Obtient les informations pour un préfixe
        
        Args:
            prefix: Préfixe (ex: 0387)
            
        Returns:
            Dictionnaire avec les informations ou None
        """
        return self.prefix_data.get(prefix)
    
    def get_operator_info(self, operator: str) -> Optional[Dict]:
        """
        Obtient les informations pour un opérateur
        
        Args:
            operator: Nom de l'opérateur
            
        Returns:
            Dictionnaire avec les informations ou None
        """
        return self.operator_data.get(operator)
    
    def get_city_info(self, city: str) -> Optional[Dict]:
        """
        Obtient les informations pour une ville
        
        Args:
            city: Nom de la ville
            
        Returns:
            Dictionnaire avec les informations ou None
        """
        return self.city_data.get(city)
    
    async def download_reference_data(self, url: Optional[str] = None) -> bool:
        """
        Télécharge des données de référence depuis une URL
        
        Args:
            url: URL optionnelle (sinon utilise les sources par défaut)
            
        Returns:
            True si le téléchargement réussit
        """
        # Pour l'instant, on utilise les données par défaut
        # On pourrait ajouter le téléchargement depuis ARCEP ou d'autres sources
        logger.info("Téléchargement des données de référence...")
        
        # Exemple: on pourrait télécharger depuis data.gouv.fr
        # https://www.data.gouv.fr/datasets/ressources-en-numerotation-telephonique
        
        # Pour l'instant, on initialise juste les données par défaut
        if not self.prefix_data:
            self._init_default_data()
            self._save_data()
        
        return True
    
    def import_from_csv(self, csv_path: Path) -> bool:
        """
        Importe des données depuis un fichier CSV
        
        Args:
            csv_path: Chemin vers le fichier CSV
            
        Returns:
            True si l'import réussit
        """
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Adapter selon le format du CSV
                    prefix = row.get('prefix', '').replace(' ', '')
                    if prefix and len(prefix) == 4:
                        self.prefix_data[prefix] = {
                            'city': row.get('city', ''),
                            'region': row.get('region', ''),
                            'department': row.get('department', ''),
                            'operator': row.get('operator', ''),
                            'postal_code': row.get('postal_code', ''),
                        }
            
            self._save_data()
            logger.info(f"Importé {len(self.prefix_data)} préfixes depuis {csv_path}")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'import CSV: {e}")
            return False

