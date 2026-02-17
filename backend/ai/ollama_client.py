"""
Client Ollama pour VocalGuard
Intègre Ollama dans le système de conversation vocale
"""

import os
import requests
from typing import Optional
from loguru import logger


class OllamaClient:
    """Client pour interagir avec l'API Ollama"""
    
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None, timeout: int = 60):
        """
        Initialise le client Ollama
        
        Args:
            base_url: URL du serveur Ollama (défaut: depuis env)
            model: Modèle à utiliser (défaut: depuis env)
            timeout: Timeout en secondes
        """
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://node15.lan:11434")).rstrip('/')
        self.model = model or os.getenv("OLLAMA_MODEL", "gemma-2b-chat")
        # Timeout depuis env ou valeur par défaut
        env_timeout = os.getenv("OLLAMA_TIMEOUT")
        self.timeout = int(env_timeout) if env_timeout else timeout
        self.conversation_history = []  # Historique de conversation
    
    def generate(self, prompt: str, use_history: bool = True) -> Optional[str]:
        """
        Génère une réponse à partir d'un prompt avec historique de conversation
        
        Args:
            prompt: Le texte à envoyer au modèle
            use_history: Si True, utilise l'historique de conversation
            
        Returns:
            La réponse du modèle ou None en cas d'erreur
        """
        url = f"{self.base_url}/api/chat"
        
        # Construire les messages avec l'historique
        messages = []
        if use_history and self.conversation_history:
            messages.extend(self.conversation_history)
        
        # Extraire les infos utilisateur de l'historique si nécessaire
        enhanced_prompt = prompt
        if use_history and self.conversation_history:
            user_info = self._extract_user_info()
            if any(word in prompt.lower() for word in ['qui', 'mon nom', 'mon prénom', 'comment je m\'appelle', 'quel est mon', 'qui suis-je']):
                if "nom" in user_info:
                    nom = user_info['nom']
                    enhanced_prompt = f"IMPORTANT: L'utilisateur s'appelle {nom}. Quand il demande 'quel est mon nom?', reponds 'TON nom est {nom}' ou 'TU es {nom}'. N'utilise JAMAIS 'mon nom' ou 'je suis' pour parler de l'utilisateur. Question: {prompt}"
        
        messages.append({
            "role": "user",
            "content": enhanced_prompt
        })
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": 80,  # Limiter la longueur pour être plus rapide
                "temperature": 0.4
            }
        }
        
        try:
            logger.debug(f"Envoi de la requête à Ollama (timeout: {self.timeout}s)")
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            assistant_response = data.get("message", {}).get("content", "")
            logger.debug(f"Réponse Ollama reçue ({len(assistant_response)} caractères)")
            
            # Mettre à jour l'historique
            if use_history and assistant_response:
                self.conversation_history.append({
                    "role": "user",
                    "content": prompt  # Utiliser le prompt original, pas enhanced
                })
                self.conversation_history.append({
                    "role": "assistant",
                    "content": assistant_response
                })
                # Limiter l'historique selon le modèle
                max_history = 12 if "fast" in self.model.lower() else 40
                if len(self.conversation_history) > max_history:
                    self.conversation_history = self.conversation_history[-max_history:]
            
            return assistant_response
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout ({self.timeout}s) lors de la requête Ollama. Le modèle est peut-être en train de charger.")
            logger.info("Astuce: Vérifiez que le service ollama-preload fonctionne pour précharger le modèle")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de la requête Ollama: {e}")
            return None
        except Exception as e:
            logger.exception(f"Erreur inattendue avec Ollama: {e}")
            return None
    
    def _extract_user_info(self) -> dict:
        """Extrait les informations sur l'utilisateur de l'historique"""
        info = {}
        for msg in self.conversation_history:
            if msg["role"] == "user":
                content = msg["content"].lower()
                if "appelle" in content or "nom" in content:
                    if "appelle" in content:
                        parts = content.split("appelle")
                        if len(parts) > 1:
                            name = parts[1].strip().split()[0:2]  # Prendre jusqu'à 2 mots
                            if name:
                                info["nom"] = " ".join(name)
        return info
    
    def clear_history(self):
        """Efface l'historique de conversation"""
        self.conversation_history = []
        logger.debug("Historique de conversation effacé")
    
    def test_connection(self) -> bool:
        """Teste la connexion au serveur Ollama"""
        try:
            url = f"{self.base_url}/api/tags"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Impossible de se connecter à Ollama: {e}")
            return False
