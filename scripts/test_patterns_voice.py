#!/usr/bin/env python3
"""
Script de test pour une boucle vocale basee sur des patterns de questions/reponses,
avec generation des reponses en WAV telephone (8 kHz mono).
"""

import asyncio
import sys
import time
import queue
from pathlib import Path

from loguru import logger

# Ajouter la racine du projet au path pour importer backend
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from backend.core.config import Config
from backend.voice.recognition import VoiceRecognition
from backend.voice.synthesis import VoiceSynthesis
from backend.voice.intents_loader import load_intents_ivr, find_intent

# Utilitaires partages pour le logging et la lecture audio
from scripts.voice_test_utils import (
    setup_logging,
    check_rpi_voice_engine,
    check_sounddevice,
    play_audio_file,
)


async def microphone_stream(
    sample_rate: int = 16000,
    channels: int = 1,
    chunk_size: int = 4000,
    max_seconds: float = 10.0,
):
    """
    Genere un flux asynchrone de chunks audio provenant du micro.

    Le flux s arrete soit apres max_seconds, soit si l appelant
    cesse de consommer l iterateur.

    Args:
        sample_rate: Taux d echantillonnage (Hz), 16000 recommande pour VOSK.
        channels: Nombre de canaux audio (1 = mono).
        chunk_size: Taille des blocs en nombre d echantillons.
        max_seconds: Duree maximum de capture avant arret.

    Yields:
        Chunks de bytes PCM 16-bit mono.
    """
    import sounddevice as sd

    audio_q: "queue.Queue[bytes]" = queue.Queue()

    def callback(indata, frames, time_info, status):
        # indata est un tableau numpy int16; on le convertit en bytes
        try:
            audio_q.put_nowait(bytes(indata))
        except Exception:
            # En cas de file pleine ou autre, on ignore pour ce chunk
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
            # Arret sur timeout global
            if time.monotonic() - start > max_seconds:
                break

            try:
                chunk = audio_q.get(timeout=0.5)
            except queue.Empty:
                continue

            if not chunk:
                continue

            yield chunk


def _load_intents(config: Config):
    """Charge les intents depuis config/intents_ivr.yaml (racine du projet VocalGuard)."""
    return load_intents_ivr(base_path=PROJECT_ROOT)


async def generate_ivr_wav(
    synthesis: VoiceSynthesis,
    text: str,
    ivr_dir: Path,
    filename: str,
) -> Path | None:
    """
    Genere un fichier WAV 8 kHz mono a partir d un texte.

    La synthese utilise le moteur configure (pyttsx3 ou gTTS), puis
    on convertit le fichier resultant au format telephone.
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        logger.error(
            "pydub n est pas installe. Installez-le avec: pip install pydub pour generer les WAV IVR."
        )
        return None

    ivr_dir.mkdir(parents=True, exist_ok=True)

    temp_audio = await synthesis.speak(text)
    if not temp_audio or not temp_audio.exists():
        logger.warning("Impossible de generer l audio TTS pour le texte IVR.")
        return None

    try:
        from audio_utils import export_wav_8k_8bit
        audio = AudioSegment.from_file(str(temp_audio))
        out_path = ivr_dir / filename
        export_wav_8k_8bit(audio, out_path)
        logger.info(f"Fichier IVR genere: {out_path} (8 kHz, 8-bit, Conexant)")
        return out_path
    except Exception as e:
        logger.exception(f"Erreur lors de la conversion en WAV IVR: {e}")
        return None


async def conversation_patterns_loop():
    """Boucle de conversation basee sur des intents (fichier config/intents_ivr.yaml)."""
    config = Config()

    intents, default_intent, exit_intent = _load_intents(config)

    recognition = VoiceRecognition(config)
    synthesis = VoiceSynthesis(config)

    await recognition.initialize()
    await synthesis.initialize()

    ivr_dir = Path(config.base_path) / "ivr_wav"

    logger.info("=" * 60)
    logger.info("Conversation vocale basee sur intents")
    logger.info("=" * 60)
    logger.info("Strategies: config/intents_ivr.yaml. WAV 8 kHz dans ivr_wav.")
    logger.info("Dites 'au revoir' ou 'quitter' pour terminer.")
    logger.info("=" * 60)
    logger.info("")

    while True:
        try:
            logger.info("Transcription en temps reel (VOSK)...")
            audio_stream = microphone_stream(sample_rate=16000, channels=1, chunk_size=4000, max_seconds=10.0)
            utterances = await recognition.stream_vosk(
                audio_stream=audio_stream,
                sample_rate=16000,
                max_utterances=1,
            )
            user_text = utterances[0] if utterances else ""

            if not user_text:
                logger.warning("Aucune transcription obtenue")
                chosen = default_intent
            else:
                logger.info(f"Vous: {user_text}")
                chosen = find_intent(user_text, intents, default_intent, exit_intent)

            response_text = chosen["response"]
            wav_filename = chosen["filename"]

            if chosen.get("name") == exit_intent.get("name"):
                wav_file = await generate_ivr_wav(synthesis, response_text, ivr_dir, wav_filename)
                if wav_file:
                    await play_audio_file(wav_file)
                break

            logger.info(f"Intent: {chosen['name']}")
            wav_file = await generate_ivr_wav(synthesis, response_text, ivr_dir, wav_filename)

            if wav_file:
                logger.info("Lecture locale du WAV (test)...")
                await play_audio_file(wav_file)

            logger.info("")
            await asyncio.sleep(0.5)

        except KeyboardInterrupt:
            logger.info("\nArret demande par l utilisateur")
            break
        except Exception as e:
            logger.exception(f"Erreur dans la boucle de conversation patterns: {e}")
            await asyncio.sleep(1)


async def main():
    """Fonction principale du test patterns."""
    setup_logging()
    check_rpi_voice_engine()

    logger.info("Initialisation de la conversation vocale basee sur des patterns...")

    # Verifier sounddevice avant la boucle d enregistrement
    check_sounddevice()

    try:
        await conversation_patterns_loop()
    except Exception as e:
        logger.exception(f"Erreur fatale dans le test patterns: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arret du test vocal patterns")

