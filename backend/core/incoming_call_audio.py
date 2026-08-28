"""
Resolution des assets audio pour la ligne entrante (WAV / TTS).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from loguru import logger

from backend.core.config import Config
from backend.core.incoming_call_types import IncomingCallAudioConfig, IncomingCallSettingsData
from backend.voice.audio_utils import write_beep_wav_8k

DEFAULT_BLOCKED_TTS = "Desole, cet appel a ete bloque."


def project_base(config: Config) -> Path:
    """
    Racine projet pour chemins relatifs.

    @param config Configuration.
    @returns Chemin base.
    """
    return Path(config.base_path) if config.base_path else Path.cwd()


def resolve_resource_path(config: Config, relative: Optional[str]) -> Optional[Path]:
    """
    Resout un chemin WAV relatif a la racine projet.

    @param config Configuration (base_path).
    @param relative Chemin relatif ou absolu.
    @returns Path absolu si le fichier existe, sinon None.
    """
    if not relative or not str(relative).strip():
        return None
    raw = Path(str(relative).strip())
    candidate = raw if raw.is_absolute() else project_base(config) / raw
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved if resolved.is_file() else None


def greeting_text(config: Config, settings: IncomingCallSettingsData) -> str:
    """
    Texte d'accueil effectif (override audio > config voicemail).

    @param config Configuration legacy.
    @param settings Settings incoming_call.
    @returns Texte TTS accueil.
    """
    custom = (settings.audio.greeting_tts_text or "").strip()
    if custom:
        return custom
    legacy = (getattr(config, "voicemail_greeting", None) or "").strip()
    if legacy:
        return legacy
    return (
        "Bonjour, vous etes bien chez DanielCraft, de Loic Daniel, "
        "merci de laisser un message."
    )


def blocked_message_text(settings: IncomingCallSettingsData) -> str:
    """
    Texte TTS pour appel bloque.

    @param settings Settings incoming_call.
    @returns Message bloque.
    """
    custom = (settings.audio.blocked_tts_text or "").strip()
    return custom or DEFAULT_BLOCKED_TTS


def ensure_default_voice_assets(config: Config) -> None:
    """
    Cree les WAV par defaut sous resources/voice/ s'ils manquent.

    @param config Configuration (base_path).
    """
    voice_dir = project_base(config) / "resources" / "voice"
    try:
        voice_dir.mkdir(parents=True, exist_ok=True)
        beep = voice_dir / "beep.wav"
        if not beep.is_file():
            write_beep_wav_8k(beep)
        blocked = voice_dir / "blocked_short.wav"
        if not blocked.is_file():
            write_beep_wav_8k(blocked, freq_hz=620, duration_ms=350)
    except OSError as exc:
        logger.warning("ensure_default_voice_assets: {}", exc)


def pick_wav_or_none(
    config: Config,
    audio: IncomingCallAudioConfig,
    *,
    source: str,
    wav_path: Optional[str],
) -> Optional[Path]:
    """
    Retourne le WAV a jouer si source=wav et fichier present.

    @param config Configuration.
    @param audio Bloc audio settings.
    @param source ``tts`` ou ``wav``.
    @param wav_path Chemin relatif configure.
    @returns Path ou None.
    """
    if source != "wav":
        return None
    return resolve_resource_path(config, wav_path)


def beep_wav_path(config: Config, audio: IncomingCallAudioConfig) -> Optional[Path]:
    """
    Chemin du bip d'enregistrement selon la config.

    @param config Configuration.
    @param audio Bloc audio.
    @returns Path WAV ou None (generation DTMF / none).
    """
    if audio.record_beep == "none":
        return None
    if audio.record_beep == "wav":
        found = resolve_resource_path(config, audio.record_beep_wav_path)
        if found:
            return found
        ensure_default_voice_assets(config)
        return resolve_resource_path(config, audio.record_beep_wav_path or "resources/voice/beep.wav")
    return None
