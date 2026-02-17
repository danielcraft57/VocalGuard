"""
Module de reconnaissance vocale
Supporte Whisper et VOSK
"""

import asyncio
from pathlib import Path
from typing import Optional
import io
from loguru import logger

from backend.core.config import Config


class VoiceRecognition:
    """Gère la reconnaissance vocale"""
    
    def __init__(self, config: Config):
        """
        Initialise le module de reconnaissance vocale
        
        Args:
            config: Configuration de l'application
        """
        self.config = config
        self.engine = config.voice_recognition_engine
        self.whisper_model = None
        self.vosk_model = None
        self.vosk_recognizer = None
    
    async def initialize(self):
        """Initialise le moteur de reconnaissance vocale"""
        logger.info(f"Initialisation de la reconnaissance vocale ({self.engine})...")
        
        if self.engine == "whisper":
            await self._init_whisper()
        elif self.engine == "vosk":
            await self._init_vosk()
        else:
            raise ValueError(f"Moteur de reconnaissance non supporté: {self.engine}")
        
        logger.info("Reconnaissance vocale initialisée")
    
    async def _init_whisper(self):
        """Initialise Whisper"""
        try:
            import whisper
            import warnings
            
            # Supprimer le warning FP16/FP32 sur CPU (c'est normal, Whisper utilise FP32 automatiquement)
            warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")
            
            logger.info(f"Chargement du modèle Whisper: {self.config.whisper_model}")
            self.whisper_model = whisper.load_model(
                self.config.whisper_model,
                device=self.config.whisper_device
            )
            logger.info("Modèle Whisper chargé")
        except ImportError:
            raise ImportError("Whisper n'est pas installé. Installez-le avec: pip install openai-whisper")
        except Exception as e:
            logger.exception(f"Erreur lors du chargement de Whisper: {e}")
            raise
    
    async def _init_vosk(self):
        """Initialise VOSK"""
        try:
            from vosk import Model, KaldiRecognizer
            import json
            
            # Trouver le modèle VOSK
            model_path = self.config.vosk_model_path
            if not model_path:
                # Chercher dans les emplacements communs
                common_paths = [
                    Path.home() / "vosk-models" / f"vosk-model-{self.config.voice_language}",
                    Path("/usr/share/vosk-models") / f"vosk-model-{self.config.voice_language}",
                ]
                
                for path in common_paths:
                    if path.exists():
                        model_path = str(path)
                        break
                
                if not model_path:
                    raise FileNotFoundError(
                        f"Modèle VOSK non trouvé. Téléchargez-le depuis https://alphacephei.com/vosk/models"
                    )
            
            logger.info(f"Chargement du modèle VOSK: {model_path}")
            self.vosk_model = Model(model_path)
            self.vosk_recognizer = KaldiRecognizer(self.vosk_model, 16000)
            self.vosk_recognizer.SetWords(True)
            logger.info("Modèle VOSK chargé")
            
        except ImportError:
            raise ImportError("VOSK n'est pas installé. Installez-le avec: pip install vosk")
        except Exception as e:
            logger.exception(f"Erreur lors du chargement de VOSK: {e}")
            raise
    
    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """
        Transcrit l'audio en texte
        
        Args:
            audio_data: Données audio brutes
            sample_rate: Taux d'échantillonnage
            
        Returns:
            Texte transcrit
        """
        if not audio_data:
            return ""
        
        logger.debug(f"Transcription de {len(audio_data)} octets d'audio")
        
        if self.engine == "whisper":
            return await self._transcribe_whisper(audio_data)
        elif self.engine == "vosk":
            return await self._transcribe_vosk(audio_data, sample_rate)
        else:
            raise ValueError(f"Moteur non supporté: {self.engine}")
    
    async def _transcribe_whisper(self, audio_data: bytes) -> str:
        """Transcrit avec Whisper"""
        try:
            import numpy as np
            import soundfile as sf
            
            # Convertir les données audio en numpy array
            audio_io = io.BytesIO(audio_data)
            audio_array, sr = sf.read(audio_io)
            
            # Whisper attend un array numpy float32
            audio_array = audio_array.astype(np.float32)
            
            # Transcrire
            result = self.whisper_model.transcribe(
                audio_array,
                language=self.config.voice_language,
                task="transcribe"
            )
            
            text = result["text"].strip()
            logger.debug(f"Transcription Whisper: {text}")
            return text
            
        except Exception as e:
            logger.exception(f"Erreur lors de la transcription Whisper: {e}")
            return ""
    
    async def _transcribe_vosk(self, audio_data: bytes, sample_rate: int) -> str:
        """Transcrit avec VOSK"""
        try:
            import json
            
            # VOSK attend des données PCM 16-bit mono
            self.vosk_recognizer.SetSampleRate(sample_rate)
            
            # Traiter les données par chunks
            text_parts = []
            chunk_size = 4000
            
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                
                if self.vosk_recognizer.AcceptWaveform(chunk):
                    result = json.loads(self.vosk_recognizer.Result())
                    if 'text' in result:
                        text_parts.append(result['text'])
            
            # Récupérer le résultat final
            final_result = json.loads(self.vosk_recognizer.FinalResult())
            if 'text' in final_result:
                text_parts.append(final_result['text'])
            
            text = ' '.join(text_parts).strip()
            logger.debug(f"Transcription VOSK: {text}")
            return text
            
        except Exception as e:
            logger.exception(f"Erreur lors de la transcription VOSK: {e}")
            return ""

