"""
Module de synthèse vocale.
Supporte pyttsx3, gTTS et edge-tts (Microsoft, nombreuses voix).
Si TTS_SERVICE_URL (ou STT_SERVICE_URL) est defini : synthese via node15.
"""

from pathlib import Path
from typing import Optional

from loguru import logger

from backend.core.config import Config
from backend.voice.tts_url import resolve_tts_service_url, resolve_tts_token


def _edge_voice_lang(voice: str) -> str:
    """
    Extrait la locale BCP-47 depuis un identifiant edge-tts.

    @param voice Identifiant voix (ex. fr-FR-DeniseNeural).
    @returns Locale pour l'enveloppe SSML.
    """
    parts = (voice or "fr-FR").split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return "fr-FR"


def _wrap_edge_ssml_if_needed(text: str, voice: str) -> str:
    """
    Enveloppe le texte dans <speak> si des balises SSML sont presentes.

    @param text Texte brut ou fragment SSML.
    @param voice Identifiant voix edge-tts (pour xml:lang).
    @returns Texte pret pour edge_tts.Communicate.
    """
    speak_text = (text or "").strip()
    if not speak_text:
        return speak_text
    lower = speak_text.lower()
    if "<speak" in lower:
        return speak_text
    markers = ("<break", "<emphasis", "<prosody", "<say-as", "<phoneme", "<sub", "<voice")
    if any(marker in lower for marker in markers):
        lang = _edge_voice_lang(voice)
        return (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="{lang}">{speak_text}</speak>'
        )
    return speak_text


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
        remote = resolve_tts_service_url(self.config)
        if remote:
            logger.info(
                "Initialisation de la synthèse vocale (distant: {})",
                remote,
            )
        else:
            logger.info(f"Initialisation de la synthèse vocale ({self.engine})...")

        if self.engine == "pyttsx3":
            ok = await self._init_pyttsx3()
            if not ok:
                logger.warning(
                    "pyttsx3 indisponible (libespeak manquant sur RPi?). Passage à gTTS. "
                    "Pour éviter: VOICE_SYNTHESIS_ENGINE=gtts dans .env ou sudo apt install espeak."
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

    async def _init_pyttsx3(self) -> bool:
        """Initialise pyttsx3. Retourne True si OK, False si indisponible (ex. libespeak manquant sur RPi)."""
        try:
            import pyttsx3

            self.pyttsx3_engine = pyttsx3.init()

            voices = self.pyttsx3_engine.getProperty("voices")
            if voices:
                lang_code = self.config.voice_language[:2]
                for voice in voices:
                    if lang_code in voice.id.lower() or lang_code in voice.name.lower():
                        self.pyttsx3_engine.setProperty("voice", voice.id)
                        logger.info("Voix sélectionnée: %s", voice.name)
                        break

            self.pyttsx3_engine.setProperty("rate", 150)
            self.pyttsx3_engine.setProperty("volume", 0.9)
            return True
        except (ImportError, OSError, Exception) as e:
            logger.debug("pyttsx3 init échoué: %s", e)
            self.pyttsx3_engine = None
            return False

    async def speak(
        self,
        text: str,
        save_to_file: Optional[Path] = None,
        *,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Génère la parole à partir du texte

        Args:
            text: Texte à prononcer
            save_to_file: Chemin optionnel pour sauvegarder l'audio
            rate: Vitesse edge-tts (ex. "+12%"), ignoré pour les autres moteurs
            pitch: Hauteur edge-tts (ex. "+2Hz"), ignoré pour les autres moteurs

        Returns:
            Chemin du fichier audio généré (si sauvegardé)
        """
        if not text:
            return None

        logger.debug(f"Synthèse vocale: {text[:50]}...")

        remote_url = resolve_tts_service_url(self.config)
        if remote_url:
            remote_path = await self._speak_remote(
                text,
                save_to_file,
                rate=rate,
                pitch=pitch,
                base_url=remote_url,
            )
            if remote_path is not None:
                return remote_path
            logger.warning(
                "TTS distant KO ({}), repli moteur local {}",
                remote_url,
                self.engine,
            )

        if self.engine == "pyttsx3":
            return await self._speak_pyttsx3(text, save_to_file)
        elif self.engine == "gtts":
            return await self._speak_gtts(text, save_to_file)
        elif self.engine == "edgetts":
            return await self._speak_edgetts(text, save_to_file, rate=rate, pitch=pitch)
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

    async def _speak_remote(
        self,
        text: str,
        save_to_file: Optional[Path] = None,
        *,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
        base_url: str,
    ) -> Optional[Path]:
        """
        Synthese via node15 ``POST /v1/tts`` (edge-tts distant).

        @param text Texte ou fragment SSML.
        @param save_to_file Destination optionnelle.
        @param rate Debit edge-tts.
        @param pitch Hauteur edge-tts.
        @param base_url URL service TTS.
        @returns Chemin fichier audio ou None si echec.
        """
        try:
            from backend.voice.node15_voice_client import Node15VoiceClient

            voice = getattr(self.config, "edge_tts_voice", None) or "fr-FR-HenriNeural"
            speech_rate = rate or getattr(self.config, "edge_tts_rate", None) or "+0%"
            speech_pitch = pitch or getattr(self.config, "edge_tts_pitch", None) or "+0Hz"
            if not save_to_file:
                save_to_file = self.cache_dir / f"temp_{hash(text)}.mp3"
            speak_text = _wrap_edge_ssml_if_needed(text, voice)
            client = Node15VoiceClient(
                base_url,
                token=resolve_tts_token(self.config),
                timeout_sec=180.0,
            )
            audio_bytes = await client.tts(
                speak_text,
                voice=voice,
                rate=speech_rate,
                pitch=speech_pitch,
            )
            if not audio_bytes:
                logger.warning("TTS distant: reponse vide")
                return None
            save_to_file = Path(save_to_file)
            save_to_file.parent.mkdir(parents=True, exist_ok=True)
            save_to_file.write_bytes(audio_bytes)
            logger.debug("Audio genere via TTS distant: {}", save_to_file)
            return save_to_file
        except Exception as exc:
            logger.warning("Erreur TTS distant: {}", exc)
            return None

    async def _speak_edgetts(
        self,
        text: str,
        save_to_file: Optional[Path] = None,
        *,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
    ) -> Optional[Path]:
        """Synthétise avec edge-tts (Microsoft, nombreuses voix)."""
        try:
            import edge_tts

            voice = getattr(self.config, "edge_tts_voice", None) or "fr-FR-HenriNeural"
            speech_rate = rate or getattr(self.config, "edge_tts_rate", None) or "+0%"
            speech_pitch = pitch or getattr(self.config, "edge_tts_pitch", None) or "+0Hz"
            if not save_to_file:
                save_to_file = self.cache_dir / f"temp_{hash(text)}.mp3"
            speak_text = _wrap_edge_ssml_if_needed(text, voice)
            communicate = edge_tts.Communicate(
                speak_text,
                voice,
                rate=speech_rate,
                pitch=speech_pitch,
            )
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
