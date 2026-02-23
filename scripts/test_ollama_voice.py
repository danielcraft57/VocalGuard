#!/usr/bin/env python3
"""
Script de test pour la conversation vocale avec Ollama
Permet de tester l'intégration Ollama + reconnaissance vocale + synthèse vocale
"""

import asyncio
import sys
import os
import time
import queue
from pathlib import Path

# Ajouter la racine du projet au path pour importer backend
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger
from backend.core.config import Config
from backend.voice.recognition import VoiceRecognition
from backend.voice.synthesis import VoiceSynthesis
from backend.ai.ollama_client import OllamaClient


def setup_logging():
    """Configure le logging"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )


def check_rpi_voice_engine():
    """Sur Raspberry Pi, Whisper provoque souvent 'Illegal instruction'. Rappel d'utiliser Vosk."""
    if os.environ.get("VOICE_RECOGNITION_ENGINE", "").lower() == "vosk":
        return
    try:
        with open("/proc/device-tree/model", "r") as f:
            if "Raspberry" in (f.read() or ""):
                logger.warning(
                    "Sur Raspberry Pi, utilisez Vosk : VOICE_RECOGNITION_ENGINE=vosk "
                    "(Whisper provoque 'Illegal instruction' sur ARM)."
                )
    except Exception:
        pass


def check_sounddevice():
    """
    Vérifie que sounddevice est utilisable (alternative a PyAudio).
    Sous Windows, sounddevice est souvent plus simple car fourni en wheel avec PortAudio.
    """
    try:
        import sounddevice as sd
        # Simple check: lister les peripheriques audio sans crasher
        sd.query_devices()
        return
    except ImportError as e:
        msg = str(e)
        if "sounddevice" in msg.lower():
            logger.error("❌ sounddevice n'est pas installe.")
            if sys.platform == "win32":
                logger.error(
                    "Sous Windows, installez via : pip install sounddevice"
                )
            else:
                logger.error("Sur Linux, installez PortAudio si besoin : sudo apt-get install portaudio19-dev")
                logger.error("Puis : pip install sounddevice")
            sys.exit(1)
        raise
    except Exception as e:
        logger.error("❌ sounddevice inutilisable : %s", e)
        sys.exit(1)


async def record_audio(duration: int = 5) -> bytes:
    """Enregistre l'audio depuis le micro"""
    try:
        import io
        import wave
        import sounddevice as sd

        CHANNELS = 1

        # Vosk est le plus a l'aise en 16 kHz mono
        RATE = 16000

        logger.info(f"🎤 Enregistrement de {duration} secondes à {RATE} Hz... Parlez maintenant !")

        frames = sd.rec(
            int(duration * RATE),
            samplerate=RATE,
            channels=CHANNELS,
            dtype="int16",
        )
        sd.wait()
        
        wav_buffer = io.BytesIO()
        wf = wave.open(wav_buffer, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16 -> 2 octets
        wf.setframerate(RATE)
        wf.writeframes(frames.tobytes())
        wf.close()
        
        logger.info("✅ Enregistrement terminé")
        return wav_buffer.getvalue()
        
    except ImportError as e:
        logger.error("❌ sounddevice n'est pas installe. Installez-le avec: pip install sounddevice")
        raise
    except Exception as e:
        logger.exception(f"Erreur lors de l'enregistrement: {e}")
        raise


async def microphone_stream(
    sample_rate: int = 16000,
    channels: int = 1,
    chunk_size: int = 4000,
    max_seconds: float = 10.0,
):
    """
    Flux asynchrone de chunks audio provenant du micro pour VOSK.
    
    Utilise sounddevice en mode RawInputStream et yield des blocs PCM 16-bit mono
    jusqu a detection de fin de flux (max_seconds).
    """
    import sounddevice as sd

    audio_q: "queue.Queue[bytes]" = queue.Queue()

    def callback(indata, frames, time_info, status):
        try:
            audio_q.put_nowait(bytes(indata))
        except Exception:
            # Si la file est pleine ou autre, on ignore ce chunk
            pass

    logger.info(f"🎤 Ecoute micro en temps reel (max {max_seconds:.1f}s)... Parlez.")

    start = time.monotonic()

    with sd.RawInputStream(
        samplerate=sample_rate,
        blocksize=chunk_size,
        dtype="int16",
        channels=channels,
        callback=callback,
    ):
        while True:
            if time.monotonic() - start > max_seconds:
                break
            try:
                chunk = audio_q.get(timeout=0.5)
            except queue.Empty:
                continue
            if not chunk:
                continue
            yield chunk


async def play_audio_file(audio_file: Path):
    """Joue un fichier audio via les haut-parleurs"""
    if not audio_file or not audio_file.exists():
        logger.warning(f"Fichier audio introuvable: {audio_file}")
        return
    
    import platform
    import subprocess
    is_windows = platform.system() == "Windows"
    is_linux = platform.system() == "Linux"
    
    # Méthode 1: Linux native (aplay/paplay) - PRIORITÉ sur Linux
    if is_linux:
        try:
            import wave
            # Calculer la durée
            try:
                with wave.open(str(audio_file), 'rb') as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    duration = frames / float(rate)
            except:
                duration = 3
            
            # Essayer aplay (ALSA) d'abord - plus fiable pour périphériques USB
            try:
                logger.info(f"🔊 Lecture audio avec aplay ({duration:.1f}s)...")
                # Utiliser la carte par défaut (configurée dans ~/.asoundrc) ou spécifier card 0
                result = subprocess.run(
                    ["aplay", "-D", "default", str(audio_file)],
                    check=True,
                    timeout=int(duration) + 5,
                    capture_output=True,
                    text=True
                )
                logger.debug("✅ Lecture aplay terminée")
                return
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
                logger.debug(f"aplay a échoué: {e}")
                # Fallback: paplay (PulseAudio)
                try:
                    logger.info(f"🔊 Lecture audio avec paplay ({duration:.1f}s)...")
                    # Démarrer PulseAudio si nécessaire
                    subprocess.run(["pulseaudio", "--start", "--exit-idle-time=-1"], 
                                 capture_output=True, timeout=2)
                    subprocess.run(["paplay", str(audio_file)], check=True, timeout=int(duration) + 5)
                    logger.debug("✅ Lecture paplay terminée")
                    return
                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                    pass
        except Exception as e:
            logger.debug(f"Erreur avec aplay/paplay: {e}")
    
    # Méthode 2: Windows native (winsound pour WAV) - PRIORITÉ sur Windows
    if is_windows:
        try:
            import winsound
            import wave
            if audio_file.suffix.lower() == '.wav':
                logger.debug("🔊 Lecture audio avec winsound (Windows natif)...")
                # Calculer la durée du fichier
                try:
                    with wave.open(str(audio_file), 'rb') as wf:
                        frames = wf.getnframes()
                        rate = wf.getframerate()
                        duration = frames / float(rate)
                        logger.debug(f"Durée du fichier: {duration:.2f}s")
                except Exception as e:
                    logger.debug(f"Impossible de calculer la durée: {e}")
                    duration = 3  # Durée par défaut si erreur
                
                # Utiliser SND_ASYNC pour ne pas bloquer, puis attendre
                logger.info(f"🔊 Lecture audio ({duration:.1f}s)...")
                winsound.PlaySound(str(audio_file), winsound.SND_FILENAME | winsound.SND_ASYNC)
                # Attendre la durée du fichier + marge
                wait_time = max(duration + 0.5, 1.0)  # Au moins 1 seconde
                await asyncio.sleep(wait_time)
                logger.debug("✅ Lecture winsound terminée")
                return
        except Exception as e:
            logger.warning(f"⚠️ Erreur avec winsound: {e}")
    
    # Méthode 3: pygame (recommandé pour tous OS)
    try:
        import pygame
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        pygame.mixer.music.load(str(audio_file))
        pygame.mixer.music.play()
        logger.debug("🔊 Lecture audio avec pygame...")
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)
        pygame.mixer.quit()
        return
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Erreur avec pygame: {e}")
    
    # Méthode 4: playsound (simple)
    try:
        from playsound import playsound
        logger.debug("🔊 Lecture audio avec playsound...")
        playsound(str(audio_file), block=False)  # Non-bloquant
        # Estimer la durée (approximatif)
        await asyncio.sleep(3)  # Durée estimée
        return
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Erreur avec playsound: {e}")
    
    # Méthode 5: pydub + simpleaudio (si disponible)
    try:
        from pydub import AudioSegment
        from pydub.playback import play
        logger.debug("Lecture audio avec pydub...")
        audio = AudioSegment.from_file(str(audio_file))
        duration_ms = len(audio)
        # Jouer dans un thread pour ne pas bloquer
        import threading
        def play_audio():
            play(audio)
        thread = threading.Thread(target=play_audio, daemon=True)
        thread.start()
        # Attendre la durée estimée
        await asyncio.sleep((duration_ms / 1000) + 0.5)
        return
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Erreur avec pydub: {e}")
    
    # Fallback: ouvrir le fichier avec le lecteur par défaut (Windows)
    if is_windows:
        try:
            import os
            logger.info("🔊 Ouverture du fichier avec le lecteur par défaut Windows...")
            os.startfile(str(audio_file))
            # Estimer la durée (basique)
            await asyncio.sleep(3)
            return
        except Exception as e:
            logger.debug(f"Impossible d'ouvrir le fichier: {e}")
    
    # Dernier recours: juste afficher le chemin
    logger.warning("⚠️ Aucune méthode de lecture audio disponible")
    logger.info(f"📁 Fichier audio généré: {audio_file}")
    if is_windows:
        logger.info("💡 Sur Windows, winsound devrait fonctionner. Vérifiez que le fichier est bien en WAV")
    elif is_linux:
        logger.info("💡 Sur Linux, installez: sudo apt-get install alsa-utils pulseaudio-utils")
        logger.info("   OU: pip install pygame")
    else:
        logger.info("💡 Alternative: pip install pygame")


async def conversation_loop():
    """Boucle de conversation avec Ollama"""
    config = Config()
    
    # Initialiser les composants
    recognition = VoiceRecognition(config)
    synthesis = VoiceSynthesis(config)
    ollama = OllamaClient()
    
    # Vérifier la connexion Ollama
    if not ollama.test_connection():
        logger.error("❌ Impossible de se connecter à Ollama")
        logger.error(f"Vérifiez que Ollama est accessible à {ollama.base_url}")
        sys.exit(1)
    
    await recognition.initialize()
    await synthesis.initialize()
    
    logger.info("=" * 60)
    logger.info("🤖 Conversation vocale avec Ollama")
    logger.info("=" * 60)
    logger.info(f"📡 Serveur: {ollama.base_url}")
    logger.info(f"🧠 Modèle: {ollama.model}")
    logger.info("💬 Dites 'au revoir' ou 'quitter' pour terminer")
    logger.info("=" * 60)
    logger.info("")
    
    # Message de bienvenue
    welcome_text = "Bonjour ! Je suis VocalGuard avec Ollama. Comment puis-je vous aider ?"
    logger.info(f"🤖 {welcome_text}")
    try:
        welcome_audio = await asyncio.wait_for(
            synthesis.speak(welcome_text),
            timeout=10.0
        )
        if welcome_audio and welcome_audio.exists():
            logger.info("🔊 Lecture du message de bienvenue...")
            await asyncio.wait_for(
                play_audio_file(welcome_audio),
                timeout=10.0
            )
        else:
            logger.warning("⚠️ Fichier audio de bienvenue non généré")
    except asyncio.TimeoutError:
        logger.warning("⏱️ Timeout lors du message de bienvenue")
    except Exception as e:
        logger.warning(f"⚠️ Erreur lors de la synthèse/jouer du bienvenue: {e}")
        logger.info("💬 Le système continue sans audio")
    
    # Verifier sounddevice avant la boucle d'enregistrement (evite des erreurs en boucle)
    check_sounddevice()
    
    while True:
        try:
            # Transcription differente selon le moteur
            if recognition.engine == "vosk":
                logger.info("🔄 Transcription VOSK en temps reel...")
                audio_stream = microphone_stream(
                    sample_rate=16000,
                    channels=1,
                    chunk_size=4000,
                    max_seconds=10.0,
                )
                utterances = await recognition.stream_vosk(
                    audio_stream=audio_stream,
                    sample_rate=16000,
                    max_utterances=1,
                )
                user_text = utterances[0] if utterances else ""
            else:
                # Fallback: enregistrement bloc + transcribe classique
                audio_data = await record_audio(duration=5)
                if not audio_data:
                    logger.warning("⚠️ Aucun audio enregistré")
                    continue
                logger.info("🔄 Transcription en cours...")
                user_text = await recognition.transcribe(audio_data)
            
            if not user_text:
                logger.warning("⚠️ Aucune transcription obtenue")
                response_text = "Je n'ai pas compris, pouvez-vous répéter ?"
            else:
                logger.info(f"👤 Vous: {user_text}")
                
                # Vérifier si l'utilisateur veut quitter
                if any(word in user_text.lower() for word in ["au revoir", "bye", "à bientôt", "quitter", "terminer"]):
                    response_text = "Au revoir ! À bientôt."
                    logger.info(f"🤖 {response_text}")
                    response_audio = await synthesis.speak(response_text)
                    if response_audio:
                        await play_audio_file(response_audio)
                    break
                
                # Générer la réponse avec Ollama
                logger.info("🧠 Génération de la réponse avec Ollama...")
                logger.info("⏳ Cela peut prendre quelques secondes...")
                response_text = ollama.generate(user_text, use_history=True)
                
                if not response_text:
                    response_text = "Désolé, la réponse prend trop de temps. Le modèle est peut-être en train de charger. Pouvez-vous réessayer ?"
            
            # Synthétiser et jouer
            logger.info(f"🤖 {response_text}")
            logger.info("🔊 Synthèse vocale en cours...")
            try:
                # Timeout pour la synthèse vocale (max 10 secondes)
                response_audio = await asyncio.wait_for(
                    synthesis.speak(response_text),
                    timeout=10.0
                )
                if response_audio and response_audio.exists():
                    logger.info(f"▶️ Lecture de la réponse...")
                    # Timeout pour la lecture (max 15 secondes)
                    await asyncio.wait_for(
                        play_audio_file(response_audio),
                        timeout=15.0
                    )
                    logger.info("✅ Réponse envoyée")
                else:
                    logger.warning("⚠️ Fichier audio non généré ou introuvable")
                    if response_audio:
                        logger.info(f"   Chemin attendu: {response_audio}")
            except asyncio.TimeoutError:
                logger.warning("⏱️ Timeout lors de la synthèse ou lecture audio")
                logger.info("💬 Réponse affichée ci-dessus (sans audio)")
            except Exception as e:
                logger.error(f"❌ Erreur lors de la synthèse/jouer: {e}")
                logger.info("💬 Réponse affichée ci-dessus (sans audio)")
            
            logger.info("")  # Ligne vide
            
            # Petite pause avant le prochain enregistrement
            await asyncio.sleep(0.5)
            
        except KeyboardInterrupt:
            logger.info("\n👋 Arrêt demandé par l'utilisateur")
            break
        except Exception as e:
            logger.exception(f"❌ Erreur dans la boucle de conversation: {e}")
            await asyncio.sleep(1)


async def main():
    """Fonction principale"""
    setup_logging()
    check_rpi_voice_engine()

    logger.info("🚀 Initialisation de la conversation vocale avec Ollama...")
    
    try:
        await conversation_loop()
    except Exception as e:
        logger.exception(f"❌ Erreur fatale: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Arrêt du test vocal")
