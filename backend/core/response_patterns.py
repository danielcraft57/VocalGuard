"""
Gestionnaire de patterns de réponses pour les conversations vocales
"""

import yaml
from pathlib import Path
from typing import List, Dict, Optional
from loguru import logger
import random


class ResponsePattern:
    """
    Représente un pattern de réponse
    
    Attributes:
        keywords: Liste de mots-clés à rechercher dans le texte utilisateur
        responses: Liste de réponses possibles (une sera choisie aléatoirement)
        priority: Priorité du pattern (plus élevé = vérifié en premier)
        exact_match: Si True, tous les mots-clés doivent être présents
    """
    
    def __init__(self, keywords: List[str], responses: List[str], priority: int = 0, exact_match: bool = False):
        self.keywords = [k.lower() for k in keywords]
        self.responses = responses
        self.priority = priority
        self.exact_match = exact_match
    
    def matches(self, text: str) -> bool:
        """
        Vérifie si le pattern correspond au texte
        
        Args:
            text: Texte de l'utilisateur
            
        Returns:
            True si le pattern correspond
        """
        text_lower = text.lower()
        
        if self.exact_match:
            # Tous les mots-clés doivent être présents
            return all(keyword in text_lower for keyword in self.keywords)
        else:
            # Au moins un mot-clé doit être présent
            return any(keyword in text_lower for keyword in self.keywords)
    
    def get_response(self) -> str:
        """
        Retourne une réponse aléatoire parmi les réponses disponibles
        
        Returns:
            Réponse choisie
        """
        return random.choice(self.responses) if self.responses else ""


class ResponsePatternManager:
    """
    Gère le chargement et l'utilisation des patterns de réponses
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialise le gestionnaire de patterns
        
        Args:
            config_path: Chemin vers le fichier de patterns (par défaut: config/responses.yaml dans le projet)
        """
        self.patterns: List[ResponsePattern] = []
        self.default_responses: List[str] = []
        self.config_path = config_path
        self._load_patterns()
    
    def _load_patterns(self):
        """Charge les patterns depuis le fichier de configuration"""
        if not self.config_path:
            # Chercher dans plusieurs emplacements
            possible_paths = [
                # Dans le répertoire config du projet
                Path(__file__).parent.parent.parent / "config" / "responses.yaml",
                # Dans le répertoire racine du projet
                Path(__file__).parent.parent.parent.parent / "config" / "responses.yaml",
            ]
            
            # Trouver le premier fichier existant
            for path in possible_paths:
                if path.exists():
                    self.config_path = path
                    break
            
            # Si aucun fichier trouvé, utiliser le premier chemin et créer le fichier
            if not self.config_path:
                self.config_path = possible_paths[0]
        
        if not self.config_path.exists():
            logger.warning(f"Fichier de patterns non trouvé: {self.config_path}. Création d'un fichier par défaut.")
            self._create_default_config()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not config:
                logger.warning("Fichier de patterns vide")
                return
            
            # Charger les patterns
            self.patterns = []
            patterns_config = config.get('patterns', [])
            
            for pattern_config in patterns_config:
                keywords = pattern_config.get('keywords', [])
                responses = pattern_config.get('responses', [])
                priority = pattern_config.get('priority', 0)
                exact_match = pattern_config.get('exact_match', False)
                
                if keywords and responses:
                    self.patterns.append(ResponsePattern(keywords, responses, priority, exact_match))
            
            # Trier par priorité (ordre décroissant)
            self.patterns.sort(key=lambda p: p.priority, reverse=True)
            
            # Charger les réponses par défaut
            self.default_responses = config.get('default_responses', [
                "J'ai bien entendu : {text}. Comment puis-je vous aider ?"
            ])
            
            logger.info(f"Chargé {len(self.patterns)} patterns de réponses depuis {self.config_path}")
            
        except Exception as e:
            logger.exception(f"Erreur lors du chargement des patterns: {e}")
            self._create_default_config()
    
    def _create_default_config(self):
        """Crée un fichier de configuration par défaut"""
        default_config = {
            'patterns': [
                {
                    'keywords': ['bonjour', 'salut', 'hello', 'bonsoir'],
                    'responses': [
                        "Bonjour ! Comment puis-je vous aider aujourd'hui ?",
                        "Salut ! Que puis-je faire pour vous ?",
                        "Bonjour ! Je suis VocalGuard, comment puis-je vous assister ?"
                    ],
                    'priority': 10
                },
                {
                    'keywords': ['au revoir', 'bye', 'à bientôt', 'salut'],
                    'responses': [
                        "Au revoir, bonne journée !",
                        "À bientôt !",
                        "Au revoir, passez une excellente journée !"
                    ],
                    'priority': 10
                },
                {
                    'keywords': ['merci', 'thanks', 'merci beaucoup'],
                    'responses': [
                        "De rien, c'est un plaisir de vous aider !",
                        "Je vous en prie !",
                        "Avec plaisir !"
                    ],
                    'priority': 8
                },
                {
                    'keywords': ['appel', 'téléphone', 'appeler'],
                    'responses': [
                        "Je peux vous aider à gérer vos appels. Que souhaitez-vous faire ?",
                        "Pour les appels, je peux vous aider. Que voulez-vous faire ?"
                    ],
                    'priority': 7
                },
                {
                    'keywords': ['bloquer', 'blocage', 'bloquer un numéro'],
                    'responses': [
                        "Je peux vous aider à bloquer des numéros indésirables.",
                        "Pour bloquer un numéro, je peux vous assister."
                    ],
                    'priority': 7
                },
                {
                    'keywords': ['message', 'vocal', 'voicemail'],
                    'responses': [
                        "Je peux gérer vos messages vocaux. Que voulez-vous faire ?",
                        "Pour les messages vocaux, je suis là pour vous aider."
                    ],
                    'priority': 7
                },
                {
                    'keywords': ['aide', 'help', 'assistance'],
                    'responses': [
                        "Je peux vous aider avec la gestion des appels, le blocage de numéros et les messages vocaux.",
                        "Je suis là pour vous aider avec VocalGuard. Que souhaitez-vous faire ?"
                    ],
                    'priority': 6
                }
            ],
            'default_responses': [
                "J'ai bien entendu : {text}. Comment puis-je vous aider ?",
                "D'accord, j'ai compris : {text}. Que souhaitez-vous faire ?",
                "Je comprends : {text}. Comment puis-je vous assister ?"
            ]
        }
        
        try:
            # Créer le répertoire si nécessaire
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            
            logger.info(f"Fichier de patterns par défaut créé: {self.config_path}")
            
        except Exception as e:
            logger.exception(f"Erreur lors de la création du fichier par défaut: {e}")
    
    def generate_response(self, user_text: str) -> str:
        """
        Génère une réponse à partir du texte de l'utilisateur
        
        Args:
            user_text: Texte de l'utilisateur
            
        Returns:
            Réponse générée
        """
        if not user_text or not user_text.strip():
            return random.choice(self.default_responses).format(text="...")
        
        # Chercher le premier pattern qui correspond
        for pattern in self.patterns:
            if pattern.matches(user_text):
                return pattern.get_response()
        
        # Aucun pattern trouvé, utiliser une réponse par défaut
        return random.choice(self.default_responses).format(text=user_text)
    
    def reload(self):
        """Recharge les patterns depuis le fichier"""
        self._load_patterns()

