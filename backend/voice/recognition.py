"""
Module de reconnaissance vocale
Supporte Whisper et VOSK
"""

import asyncio
from pathlib import Path
from typing import Optional, AsyncIterator, List
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
        self._out_stream_recs: dict[str, object] = {}
    
    async def initialize(self):
        """Initialise le moteur de reconnaissance vocale"""
        logger.info(f"Initialisation de la reconnaissance vocale ({self.engine})...")
        
        # gtts est un moteur de synthèse (texte -> parole), pas de reconnaissance
        if self.engine == "gtts":
            logger.warning(
                "VOICE_RECOGNITION_ENGINE=gtts est invalide (gtts sert à la synthèse vocale). "
                "Utilisation de Vosk pour la reconnaissance."
            )
            self.engine = "vosk"
        
        if self.engine == "whisper":
            ok = await self._init_whisper()
            if not ok:
                logger.warning(
                    "Whisper indisponible. Passage à Vosk. "
                    "Pour éviter: VOICE_RECOGNITION_ENGINE=vosk dans .env"
                )
                self.engine = "vosk"
        if self.engine == "vosk":
            ok = await self._init_vosk()
            if not ok:
                logger.warning(
                    "VOSK indisponible (modèle non trouvé). "
                    "Appels sans transcription. Télécharger un modèle: https://alphacephei.com/vosk/models "
                    "ou définir VOSK_MODEL_PATH dans .env"
                )
                self.engine = None
        if self.engine not in ("whisper", "vosk"):
            if self.engine is None:
                logger.info("Reconnaissance vocale désactivée (aucun moteur disponible)")
                return
            raise ValueError(
                f"Moteur de reconnaissance non supporté: {self.engine}. "
                "Utiliser 'whisper' ou 'vosk'. (gtts est pour VOICE_SYNTHESIS_ENGINE.)"
            )
        logger.info("Reconnaissance vocale initialisée")
    
    async def _init_whisper(self) -> bool:
        """Initialise Whisper. Retourne True si OK, False si indisponible."""
        try:
            import whisper
            import warnings

            warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")
            logger.info("Chargement du modèle Whisper: %s", self.config.whisper_model)
            self.whisper_model = whisper.load_model(
                self.config.whisper_model,
                device=self.config.whisper_device,
            )
            logger.info("Modèle Whisper chargé")
            return True
        except (ImportError, OSError, Exception) as e:
            logger.debug("Whisper init échoué: %s", e)
            self.whisper_model = None
            return False
    
    async def _init_vosk(self) -> bool:
        """Initialise VOSK. Retourne True si OK, False si modèle absent ou erreur."""
        try:
            from vosk import Model, KaldiRecognizer

            model_path = self.config.vosk_model_path
            if not model_path:
                common_paths = [
                    Path.home() / "vosk-models" / f"vosk-model-{self.config.voice_language}",
                    Path.home() / "vosk-models" / f"vosk-model-{self.config.voice_language}-0.22",
                    Path("/usr/share/vosk-models") / f"vosk-model-{self.config.voice_language}",
                ]
                for path in common_paths:
                    if path.exists():
                        model_path = str(path)
                        break
                if not model_path:
                    logger.debug("Modèle VOSK non trouvé dans les emplacements par défaut")
                    return False

            logger.info("Chargement du modèle VOSK: %s", model_path)
            self.vosk_model = Model(model_path)
            self.vosk_recognizer = KaldiRecognizer(self.vosk_model, 16000)
            self.vosk_recognizer.SetWords(True)
            logger.info("Modèle VOSK chargé")
            return True
        except (ImportError, FileNotFoundError, OSError, Exception) as e:
            logger.debug("VOSK init échoué: %s", e)
            self.vosk_model = None
            self.vosk_recognizer = None
            return False
    
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
        if self.engine is None:
            return ""

        logger.debug("Transcription de %s octets d'audio", len(audio_data))
        if self.engine == "whisper":
            return await self._transcribe_whisper(audio_data)
        if self.engine == "vosk":
            return await self._transcribe_vosk(audio_data, sample_rate)
        return ""
    
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
            
            # VOSK attend des données PCM 16-bit mono.
            # Le recognizer est initialisé avec un sample rate fixe (16000 Hz).
            # On remet l'état du recognizer à zéro pour chaque nouvelle séquence.
            if self.vosk_recognizer is None:
                await self._init_vosk()
            else:
                self.vosk_recognizer.Reset()
            
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

    def outgoing_stream_start(self, session_key: str) -> bool:
        """
        Demarre un recognizer VOSK dedie pour une session (ex. appel sortant) sans Reset entre chunks.
        Retourne False si VOSK indisponible.
        """
        if self.engine != "vosk" or not self.vosk_model:
            return False
        try:
            from vosk import KaldiRecognizer

            self.outgoing_stream_end(session_key)
            r = KaldiRecognizer(self.vosk_model, 16000)
            r.SetWords(True)
            self._out_stream_recs[session_key] = r
            return True
        except Exception as e:
            logger.warning("outgoing_stream_start: {}", e)
            return False

    def outgoing_stream_feed(self, session_key: str, pcm16: bytes) -> tuple[Optional[str], list[str]]:
        """
        Alimente le flux VOSK avec du PCM s16le 16 kHz mono.

        Returns:
            (texte_partiel pour affichage live, segments de phrase finalises dans ce bloc)
        """
        rec = self._out_stream_recs.get(session_key)
        if not rec or not pcm16:
            return (None, [])
        try:
            import json

            segments: list[str] = []
            step = 4000
            for i in range(0, len(pcm16), step):
                chunk = pcm16[i : i + step]
                if rec.AcceptWaveform(chunk):
                    r = json.loads(rec.Result())
                    t = (r.get("text") or "").strip()
                    if t:
                        segments.append(t)
            partial = json.loads(rec.PartialResult())
            pt = (partial.get("partial") or "").strip()
            return (pt or None, segments)
        except Exception as e:
            logger.debug("outgoing_stream_feed: {}", e)
            return (None, [])

    def outgoing_stream_end(self, session_key: str) -> str:
        """Termine la session streaming et retourne le dernier texte VOSK (reste du buffer)."""
        rec = self._out_stream_recs.pop(session_key, None)
        if rec is None:
            return ""
        try:
            import json

            final = json.loads(rec.FinalResult())
            return (final.get("text") or "").strip()
        except Exception:
            return ""

    async def stream_vosk(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int = 16000,
        max_utterances: int = 1,
    ) -> List[str]:
        """
        Transcription VOSK en temps reel a partir d un flux de chunks audio.
        
        Le principe:
        - On alimente VOSK chunk par chunk (PCM 16-bit mono).
        - A chaque fois qu AcceptWaveform() renvoie True, VOSK considere qu il a
          une phrase complete (fin de phrase / pause suffisante).
        - On collecte ces phrases jusqu a max_utterances, puis on s arrete.
        
        Args:
            audio_stream: Flux asynchrone de bytes PCM 16-bit mono.
            sample_rate: Taux d echantillonnage des chunks (par defaut 16000 Hz).
            max_utterances: Nombre maximum de phrases a retourner avant d arreter.
        
        Returns:
            Liste de phrases reconnues (une entree par fin de phrase detectee).
        """
        if self.engine != "vosk":
            raise ValueError("stream_vosk ne fonctionne que avec le moteur VOSK")
        if not self.vosk_model:
            await self._init_vosk()

        try:
            from vosk import KaldiRecognizer
            import json
        except ImportError as e:
            raise ImportError("VOSK n'est pas installé. Installez-le avec: pip install vosk") from e

        recognizer = KaldiRecognizer(self.vosk_model, sample_rate)
        recognizer.SetWords(True)

        utterances: List[str] = []

        try:
            async for chunk in audio_stream:
                if not chunk:
                    continue

                # AcceptWaveform renvoie True quand VOSK estime avoir une phrase complete
                if recognizer.AcceptWaveform(chunk):
                    result = json.loads(recognizer.Result())
                    text = (result.get("text") or "").strip()
                    if text:
                        utterances.append(text)
                        logger.debug(f"Transcription VOSK (phrase terminee): {text}")
                    if len(utterances) >= max_utterances:
                        break
                else:
                    # Resultat partiel (en cours de phrase)
                    partial = json.loads(recognizer.PartialResult())
                    partial_text = (partial.get("partial") or "").strip()
                    if partial_text:
                        logger.debug(f"Transcription VOSK (partielle): {partial_text}")

            # Resultat final apres la fin du flux
            final_result = json.loads(recognizer.FinalResult())
            final_text = (final_result.get("text") or "").strip()
            if final_text:
                utterances.append(final_text)
                logger.debug(f"Transcription VOSK (finale): {final_text}")

            return utterances

        except Exception as e:
            logger.exception(f"Erreur lors de la transcription VOSK en flux: {e}")
            return []

