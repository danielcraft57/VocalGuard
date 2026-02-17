# Test de l'interface vocale en local

Ce script permet de tester l'interface vocale de VocalGuard sans modem, en utilisant le micro et les haut-parleurs de votre PC.

## Prérequis

- Python 3.9+ (ou 3.13+)
- Microphone fonctionnel
- Haut-parleurs ou casque audio
- Les dépendances installées : `pyaudio`, `pygame` (ou `playsound`)

## Installation des dépendances

```bash
pip install pyaudio pygame
```

**Note pour Windows** : `pyaudio` peut nécessiter l'installation de `pipwin` :
```bash
pip install pipwin
pipwin install pyaudio
```

## Utilisation

### Via le script Python

```bash
python scripts/test_voice_conversation.py
```

Le script va :
1. Initialiser la reconnaissance vocale (Whisper ou VOSK)
2. Initialiser la synthèse vocale (pyttsx3 ou gTTS)
3. Démarrer une boucle de conversation interactive
4. Enregistrer votre voix pendant 5 secondes
5. Transcrire votre message
6. Générer une réponse automatique
7. Synthétiser et jouer la réponse

### Via l'interface web

1. Démarrez l'application : `.\run.ps1` (Windows) ou `./run.sh` (Linux/Mac)
2. Ouvrez votre navigateur : `http://localhost:8000`
3. Cliquez sur l'onglet "Test vocal"
4. Utilisez les trois sections :
   - **Synthèse vocale** : Entrez un texte et générez l'audio
   - **Reconnaissance vocale** : Uploadez un fichier audio pour le transcrire
   - **Test de conversation** : Uploadez un fichier audio, le système génère une réponse et la synthétise

## Personnalisation des réponses

Pour personnaliser les réponses de conversation, modifiez la fonction `generate_response()` dans :
- `scripts/test_voice_conversation.py` (pour le script Python)
- `vocalguard/api/routes/voice_test.py` (pour l'API web)

Vous pouvez ajouter vos propres règles de conversation, intégrer un chatbot, ou utiliser des modèles de langage pour des réponses plus intelligentes.

## Exemple de conversation

```
VocalGuard: Bonjour ! Je suis VocalGuard. Comment puis-je vous aider ?
Vous: Bonjour, je veux bloquer un numéro
VocalGuard: Je peux vous aider à bloquer des numéros indésirables.
Vous: Merci
VocalGuard: De rien, c'est un plaisir de vous aider !
Vous: Au revoir
VocalGuard: Au revoir ! À bientôt.
```

## Dépannage

### Erreur "pyaudio not found"
Installez pyaudio avec `pip install pyaudio` ou `pipwin install pyaudio` (Windows)

### Erreur "No module named 'pygame'"
Installez pygame avec `pip install pygame` ou utilisez `playsound` à la place

### Le micro ne fonctionne pas
Vérifiez que votre microphone est bien connecté et autorisé dans les paramètres système

### La transcription est vide
Vérifiez que le fichier audio est au bon format (WAV, 16kHz recommandé) et que le volume est suffisant

