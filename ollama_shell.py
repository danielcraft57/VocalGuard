#!/usr/bin/env python3
"""
Shell interactif pour interagir avec Ollama sur node15.lan
"""

import requests
import json
import sys
from typing import Optional

# Configuration par défaut
DEFAULT_BASE_URL = "http://node15.lan:11434"
DEFAULT_MODEL = "gemma-2b-chat"  # Modèle optimisé pour conversations avec historique (recommandé)
DEFAULT_TIMEOUT = 120  # 2 minutes pour les réponses longues


class OllamaClient:
    """Client pour interagir avec l'API Ollama"""
    
    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.conversation_history = []  # Historique de conversation
    
    def generate(self, prompt: str, stream: bool = False, show_progress: bool = True, use_history: bool = True) -> Optional[str]:
        """
        Génère une réponse à partir d'un prompt avec historique de conversation
        
        Args:
            prompt: Le texte à envoyer au modèle
            stream: Si True, retourne un générateur pour le streaming
            show_progress: Si True, affiche un indicateur de progression
            use_history: Si True, utilise l'historique de conversation
            
        Returns:
            La réponse du modèle ou None en cas d'erreur
        """
        url = f"{self.base_url}/api/chat"
        
        # Construire les messages avec l'historique
        messages = []
        
        if use_history and self.conversation_history:
            # Ajouter l'historique
            messages.extend(self.conversation_history)
        
        # Ajouter le nouveau message avec clarification des rôles si nécessaire
        enhanced_prompt = prompt
        if use_history and self.conversation_history:
            # Extraire les infos utilisateur de l'historique
            user_info = self.extract_user_info()
            
            # Pour les questions référentielles, reformuler pour être plus explicite
            if any(word in prompt.lower() for word in ['qui', 'mon nom', 'mon prénom', 'comment je m\'appelle', 'quel est mon', 'qui suis-je']):
                if "nom" in user_info:
                    nom = user_info['nom']
                    enhanced_prompt = f"IMPORTANT: L'utilisateur s'appelle {nom}. Quand il demande 'quel est mon nom?', reponds 'TON nom est {nom}' ou 'TU es {nom}'. N'utilise JAMAIS 'mon nom' ou 'je suis' pour parler de l'utilisateur. Question: {prompt}"
                else:
                    enhanced_prompt = f"Rappel: L'utilisateur a parlé de lui-même dans la conversation précédente. {prompt}"
        
        messages.append({
            "role": "user",
            "content": enhanced_prompt
        })
        
        # Debug: afficher les messages envoyés (optionnel, peut être désactivé)
        # print(f"\n[DEBUG] Envoi de {len(messages)} messages", file=sys.stderr)
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream
        }
        
        try:
            if show_progress and not stream:
                print("Generation en cours...", end="", flush=True)
            
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if show_progress and not stream:
                print("\r" + " " * 30 + "\r", end="")  # Efface le message de progression
            
            assistant_response = data.get("message", {}).get("content", "")
            
            # Mettre à jour l'historique
            if use_history and assistant_response:
                self.conversation_history.append({
                    "role": "user",
                    "content": prompt
                })
                self.conversation_history.append({
                    "role": "assistant",
                    "content": assistant_response
                })
                # Limiter l'historique à 6 échanges (12 messages) pour le modèle rapide avec contexte limité
                # gemma-2b-fast a seulement 512 tokens de contexte
                max_history = 12 if "fast" in self.model.lower() else 40
                if len(self.conversation_history) > max_history:
                    self.conversation_history = self.conversation_history[-max_history:]
            
            return assistant_response
        except requests.exceptions.Timeout:
            if show_progress:
                print("\r" + " " * 30 + "\r", end="")
            print("Timeout: La reponse prend trop de temps. Le modele est peut-etre en train de charger.", file=sys.stderr)
            return None
        except requests.exceptions.RequestException as e:
            if show_progress:
                print("\r" + " " * 30 + "\r", end="")
            print(f"Erreur lors de la requete: {e}", file=sys.stderr)
            return None
    
    def clear_history(self):
        """Efface l'historique de conversation"""
        self.conversation_history = []
    
    def extract_user_info(self) -> dict:
        """Extrait les informations sur l'utilisateur de l'historique"""
        info = {}
        for msg in self.conversation_history:
            if msg["role"] == "user":
                content = msg["content"].lower()
                # Extraire le nom
                if "appelle" in content or "nom" in content:
                    if "appelle" in content:
                        parts = content.split("appelle")
                        if len(parts) > 1:
                            name = parts[1].strip().split()[0:2]  # Prendre jusqu'à 2 mots (prénom nom)
                            if name:
                                info["nom"] = " ".join(name)
        return info
    
    def list_models(self) -> list:
        """Liste les modèles disponibles"""
        url = f"{self.base_url}/api/tags"
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return [model["name"] for model in data.get("models", [])]
        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de la récupération des modèles: {e}", file=sys.stderr)
            return []
    
    def test_connection(self) -> bool:
        """Teste la connexion au serveur Ollama"""
        try:
            models = self.list_models()
            if models:
                print(f"[OK] Connexion reussie! Modeles disponibles: {', '.join(models)}")
                return True
            else:
                print("[ERREUR] Connexion reussie mais aucun modele trouve", file=sys.stderr)
                return False
        except Exception as e:
            print(f"[ERREUR] Erreur de connexion: {e}", file=sys.stderr)
            return False


def interactive_shell():
    """Lance un shell interactif"""
    print("=" * 60)
    print("Shell Ollama - Connexion à node15.lan")
    print("=" * 60)
    print()
    
    # Test de connexion
    client = OllamaClient()
    if not client.test_connection():
        print("\nImpossible de se connecter au serveur Ollama.")
        print(f"Vérifie que le serveur est accessible à {DEFAULT_BASE_URL}")
        sys.exit(1)
    
    print(f"\nModèle actuel: {client.model}")
    print("Tape 'quit' ou 'exit' pour quitter")
    print("Tape 'model <nom>' pour changer de modèle")
    print("Tape 'list' pour lister les modèles disponibles")
    print("-" * 60)
    print()
    
    while True:
        try:
            # Lecture de la commande
            user_input = input("Vous: ").strip()
            
            if not user_input:
                continue
            
            # Commandes spéciales
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Au revoir!")
                break
            
            if user_input.lower() == 'list':
                models = client.list_models()
                print(f"Modèles disponibles: {', '.join(models)}")
                continue
            
            if user_input.lower().startswith('model '):
                new_model = user_input[6:].strip()
                if new_model in client.list_models():
                    client.model = new_model
                    client.clear_history()  # Effacer l'historique lors du changement de modèle
                    print(f"Modèle changé pour: {new_model} (historique effacé)")
                else:
                    print(f"Modèle '{new_model}' non trouvé")
                continue
            
            if user_input.lower() == 'clear':
                client.clear_history()
                print("Historique de conversation effacé")
                continue
            
            # Génération de réponse
            print("Assistant: ", end="", flush=True)
            # Forcer le français si le modèle est basé sur phi (gemma respecte mieux les instructions)
            if "phi" in client.model.lower() and "gemma" not in client.model.lower():
                prompt = f"Reponds UNIQUEMENT en francais, de maniere breve et naturelle: {user_input}"
            else:
                prompt = user_input
            response = client.generate(prompt, show_progress=True)
            if response:
                print(response)
            else:
                print("[ERREUR] Erreur lors de la generation de la reponse")
            print()
            
        except KeyboardInterrupt:
            print("\n\nAu revoir!")
            break
        except EOFError:
            print("\n\nAu revoir!")
            break


if __name__ == "__main__":
    # Si des arguments sont passés, on fait une requête unique (sans historique)
    if len(sys.argv) > 1:
        user_prompt = " ".join(sys.argv[1:])
        client = OllamaClient()
        # Forcer le français si le modèle est basé sur phi (gemma respecte mieux les instructions)
        if "phi" in client.model.lower() and "gemma" not in client.model.lower():
            prompt = f"Reponds UNIQUEMENT en francais, de maniere breve et naturelle: {user_prompt}"
        else:
            prompt = user_prompt
        response = client.generate(prompt, use_history=False)  # Pas d'historique pour les requêtes uniques
        if response:
            print(response)
        else:
            sys.exit(1)
    else:
        # Sinon, on lance le shell interactif (avec historique)
        interactive_shell()

