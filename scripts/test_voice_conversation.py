#!/usr/bin/env python3
"""
Script de test pour l'interface vocale en local
Utilise le micro et les haut-parleurs du PC pour simuler une conversation
"""

import asyncio
import sys
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from backend.core.config import Config
from backend.core.response_patterns import ResponsePatternManager
from backend.voice.recognition import VoiceRecognition
from backend.voice.synthesis import VoiceSynthesis


def setup_logging():
    """Configure le logging"""
    logger.remove()
    logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>", level="INFO")




async def record_audio(duration: int = 5) -> bytes:
    """
    Enregistre l'audio depuis le micro
    
    Args:
        duration: Durée d'enregistrement en secondes
        
    Returns:
        Données audio brutes
    """
    try:
        import pyaudio
        import wave
        import io
        
        # Configuration audio
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        
        audio = pyaudio.PyAudio()
        
        logger.info(f"Enregistrement de {duration} secondes... Parlez maintenant !")
        
        stream = audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
        
        frames = []
        for _ in range(0, int(RATE / CHUNK * duration)):
            data = stream.read(CHUNK)
            frames.append(data)
        
        stream.stop_stream()
        stream.close()
        audio.terminate()
        
        # Convertir en WAV
        wav_buffer = io.BytesIO()
        wf = wave.open(wav_buffer, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        logger.info("Enregistrement terminé")
        return wav_buffer.getvalue()
        
    except ImportError:
        logger.error("pyaudio n'est pas installé. Installez-le avec: pip install pyaudio")
        raise
    except Exception as e:
        logger.exception(f"Erreur lors de l'enregistrement: {e}")
        raise


async def play_audio_file(audio_file: Path):
    """
    Joue un fichier audio via les haut-parleurs
    
    Args:
        audio_file: Chemin du fichier audio
    """
    try:
        import pygame
        
        pygame.mixer.init()
        pygame.mixer.music.load(str(audio_file))
        pygame.mixer.music.play()
        
        # Attendre que la lecture soit terminée
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)
            
    except ImportError:
        # Fallback : utiliser playsound ou autre
        try:
            from playsound import playsound
            playsound(str(audio_file))
        except ImportError:
            logger.warning("Aucune bibliothèque de lecture audio trouvée. Installez pygame ou playsound.")
            logger.info(f"Fichier audio généré: {audio_file}")
    except Exception as e:
        logger.exception(f"Erreur lors de la lecture audio: {e}")


async def conversation_loop(config: Config):
    """
    Boucle de conversation interactive basée sur patterns.
    
    Args:
        config: Configuration de l'application
    """
    recognition = VoiceRecognition(config)
    synthesis = VoiceSynthesis(config)
    
    config_path = None
    if config.config_path:
        config_path = config.config_path.parent / "responses.yaml"
    elif config.base_path:
        config_path = config.base_path / "responses.yaml"
    pattern_manager = ResponsePatternManager(config_path)
    
    await recognition.initialize()
    await synthesis.initialize()
    
    logger.info("=== Test de conversation vocale ===")
    logger.info("Mode: Patterns + ML local (réponses prédéfinies)")
    logger.info("Dites 'au revoir' pour quitter")
    logger.info("")
    
    # Message de bienvenue
    welcome_text = "Bonjour ! Je suis VocalGuard. Comment puis-je vous aider ?"
    logger.info(f"VocalGuard: {welcome_text}")
    welcome_audio = await synthesis.speak(welcome_text)
    if welcome_audio:
        await play_audio_file(welcome_audio)
    
    while True:
        try:
            # Enregistrer l'utilisateur
            audio_data = await record_audio(duration=5)
            
            if not audio_data:
                logger.warning("Aucun audio enregistré")
                continue
            
            # Transcrire
            logger.info("Transcription en cours...")
            user_text = await recognition.transcribe(audio_data)
            
            if not user_text:
                logger.warning("Aucune transcription obtenue")
                response_text = "Je n'ai pas compris, pouvez-vous répéter ?"
            else:
                logger.info(f"Vous: {user_text}")
                
                # Vérifier si l'utilisateur veut quitter
                if any(word in user_text.lower() for word in ["au revoir", "bye", "à bientôt", "quitter", "terminer"]):
                    response_text = "Au revoir ! À bientôt."
                    logger.info(f"VocalGuard: {response_text}")
                    response_audio = await synthesis.speak(response_text)
                    if response_audio:
                        await play_audio_file(response_audio)
                    break
                
                # Générer la réponse via patterns
                response_text = pattern_manager.generate_response(user_text)
            
            # Synthétiser et jouer la réponse
            logger.info(f"VocalGuard: {response_text}")
            response_audio = await synthesis.speak(response_text)
            if response_audio:
                await play_audio_file(response_audio)
            
            logger.info("")  # Ligne vide pour la lisibilité
            
        except KeyboardInterrupt:
            logger.info("\nArrêt demandé par l'utilisateur")
            break
        except Exception as e:
            logger.exception(f"Erreur dans la boucle de conversation: {e}")
            await asyncio.sleep(1)


async def main():
    """Fonction principale"""
    setup_logging()
    
    logger.info("Initialisation du test vocal...")
    
    config = Config()
    
    try:
        await conversation_loop(config)
    except Exception as e:
        logger.exception(f"Erreur fatale: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arrêt du test vocal")

