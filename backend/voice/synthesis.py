"""
Module de synthèse vocale.
Supporte pyttsx3, gTTS et edge-tts (Microsoft, nombreuses voix).
"""

import asyncio
from pathlib import Path
from typing import Optional
from loguru import logger

from backend.core.config import Config


class VoiceSynthesis:
    """Gère la synthèse vocale"""
    
    def __init__(self, config: Config):
        """
        Initialise le module de synthèse vocale
        
        Args:
            config: Configuration de l'application
        """
        self.config = config
        self.engine = config.voice_synthesis_engine
        self.pyttsx3_engine = None
        self.cache_dir = Path(config.base_path) / "audio_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    async def initialize(self):
        """Initialise le moteur de synthèse vocale"""
        logger.info(f"Initialisation de la synthèse vocale ({self.engine})...")
        
        if self.engine == "pyttsx3":
            try:
                await self._init_pyttsx3()
            except (ImportError, Exception) as e:
                logger.warning(
                    "pyttsx3 indisponible (%s). Passage à gTTS. "
                    "Pour éviter ce message, définir VOICE_SYNTHESIS_ENGINE=gtts dans .env",
                    e,
                )
                self.engine = "gtts"
        elif self.engine == "gtts":
            # gTTS n'a pas besoin d'initialisation
            pass
        elif self.engine == "edgetts":
            # edge-tts n'a pas besoin d'init; la voix est dans config.edge_tts_voice
            pass
        else:
            raise ValueError(f"Moteur de synthèse non supporté: {self.engine}")
        
        logger.info("Synthèse vocale initialisée")
    
    async def _init_pyttsx3(self):
        """Initialise pyttsx3"""
        try:
            import pyttsx3
            
            self.pyttsx3_engine = pyttsx3.init()
            
            # Configurer la voix selon la langue
            voices = self.pyttsx3_engine.getProperty('voices')
            if voices:
                # Chercher une voix dans la langue configurée
                lang_code = self.config.voice_language[:2]
                for voice in voices:
                    if lang_code in voice.id.lower() or lang_code in voice.name.lower():
                        self.pyttsx3_engine.setProperty('voice', voice.id)
                        logger.info(f"Voix sélectionnée: {voice.name}")
                        break
            
            # Configurer la vitesse et le volume
            self.pyttsx3_engine.setProperty('rate', 150)  # Vitesse de parole
            self.pyttsx3_engine.setProperty('volume', 0.9)  # Volume
            
        except ImportError as e:
            raise ImportError(
                "pyttsx3 n'est pas installé ou pywin32 manque. "
                "Installez avec: pip install pyttsx3 pywin32. "
                "Sinon utilisez gTTS: VOICE_SYNTHESIS_ENGINE=gtts dans .env"
            ) from e
        except Exception as e:
            logger.exception(f"Erreur lors de l'initialisation de pyttsx3: {e}")
            raise
    
    async def speak(self, text: str, save_to_file: Optional[Path] = None) -> Optional[Path]:
        """
        Génère la parole à partir du texte
        
        Args:
            text: Texte à prononcer
            save_to_file: Chemin optionnel pour sauvegarder l'audio
            
        Returns:
            Chemin du fichier audio généré (si sauvegardé)
        """
        if not text:
            return None
        
        logger.debug(f"Synthèse vocale: {text[:50]}...")
        
        if self.engine == "pyttsx3":
            return await self._speak_pyttsx3(text, save_to_file)
        elif self.engine == "gtts":
            return await self._speak_gtts(text, save_to_file)
        elif self.engine == "edgetts":
            return await self._speak_edgetts(text, save_to_file)
        else:
            raise ValueError(f"Moteur non supporté: {self.engine}")
    
    async def _speak_pyttsx3(self, text: str, save_to_file: Optional[Path] = None) -> Optional[Path]:
        """Synthétise avec pyttsx3"""
        try:
            if save_to_file:
                # Sauvegarder dans un fichier
                self.pyttsx3_engine.save_to_file(text, str(save_to_file))
                self.pyttsx3_engine.runAndWait()
                logger.debug(f"Audio sauvegardé: {save_to_file}")
                return save_to_file
            else:
                # Parler directement (pour les tests)
                # En production, on sauvegarde toujours dans un fichier
                # pour pouvoir le jouer via le modem
                temp_file = self.cache_dir / f"temp_{hash(text)}.wav"
                self.pyttsx3_engine.save_to_file(text, str(temp_file))
                self.pyttsx3_engine.runAndWait()
                return temp_file
                
        except Exception as e:
            logger.exception(f"Erreur lors de la synthèse pyttsx3: {e}")
            return None
    
    async def _speak_gtts(self, text: str, save_to_file: Optional[Path] = None) -> Optional[Path]:
        """Synthétise avec gTTS"""
        try:
            from gtts import gTTS
            import tempfile
            
            # Créer le fichier temporaire si non spécifié
            if not save_to_file:
                save_to_file = self.cache_dir / f"temp_{hash(text)}.mp3"
            
            # Générer l'audio
            tts = gTTS(text=text, lang=self.config.voice_language, slow=False)
            tts.save(str(save_to_file))
            
            logger.debug(f"Audio généré avec gTTS: {save_to_file}")
            return save_to_file
            
        except Exception as e:
            logger.exception(f"Erreur lors de la synthèse gTTS: {e}")
            return None

    async def _speak_edgetts(self, text: str, save_to_file: Optional[Path] = None) -> Optional[Path]:
        """Synthétise avec edge-tts (Microsoft, nombreuses voix)."""
        try:
            import edge_tts
            voice = getattr(self.config, "edge_tts_voice", None) or "fr-FR-DeniseNeural"
            if not save_to_file:
                save_to_file = self.cache_dir / f"temp_{hash(text)}.mp3"
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(save_to_file))
            logger.debug(f"Audio généré avec edge-tts: {save_to_file}")
            return save_to_file
        except Exception as e:
            logger.exception(f"Erreur lors de la synthèse edge-tts: {e}")
            return None

    async def play_audio(self, audio_file: Path):
        """
        Joue un fichier audio (via le modem ou le système)
        
        Args:
            audio_file: Chemin du fichier audio
        """
        # TODO: Implémenter la lecture audio via le modem
        # Pour l'instant, c'est géré par le CallManager
        logger.debug(f"Lecture audio: {audio_file}")

