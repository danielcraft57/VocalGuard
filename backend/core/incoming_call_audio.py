"""
Mise a jour des chemins audio accueil et assets voice (layout resources/voice/).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from loguru import logger

from backend.core.config import Config
from backend.core.incoming_call_types import IncomingCallAudioConfig, IncomingCallSettingsData
from backend.voice.audio_utils import (
    write_beep_wav_8k,
    write_greeting_intro_wav,
)
from backend.voice.audio_utils import recommended_edge_tts_pitch_for_jingle
from backend.voice.voice_paths import (
    BEEP_WAV,
    BLOCKED_WAV,
    INTRO_DEFAULT_WAV,
    WHISPERING_ICELAND_MP3,
    ensure_voice_tree,
    intro_variant_path,
    resolve_beep_wav,
    resolve_blocked_wav,
    resolve_intro_wav,
    resolve_voice_asset,
    voice_root,
)

DEFAULT_BLOCKED_TTS = "Desole, cet appel a ete bloque."
DEFAULT_GREETING_TTS = (
    "Bonjour, Monsieur Daniel est absent. Merci de laisser un message apres le bip."
)


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
    return resolve_voice_asset(project_base(config), relative)


def greeting_text(config: Config, settings: IncomingCallSettingsData) -> str:
    """
    Texte d'accueil effectif (override audio > config voicemail).

    @param config Configuration legacy.
    @param settings Settings incoming_call.
    @returns Texte TTS accueil.
    """
    custom = (settings.audio.greeting_tts_text or "").strip()
    if custom:
        # YAML multiligne : une seule ligne pour TTS + cle cache stable.
        return " ".join(custom.split())
    legacy = (getattr(config, "voicemail_greeting", None) or "").strip()
    if legacy:
        return legacy
    return DEFAULT_GREETING_TTS


def sync_edge_tts_from_audio(config: Config, audio: IncomingCallAudioConfig) -> None:
    """
    Copie voix / debit / hauteur TTS depuis le bloc audio vers Config runtime.

    @param config Configuration a muter.
    @param audio Bloc audio incoming_call.
    """
    if audio.edge_tts_rate:
        config.edge_tts_rate = str(audio.edge_tts_rate)
    if audio.edge_tts_voice:
        config.edge_tts_voice = str(audio.edge_tts_voice)
    pitch = (audio.edge_tts_pitch or "").strip()
    intro_mode = getattr(audio, "greeting_intro_mode", "none") or "none"
    intro_variant = getattr(audio, "greeting_intro_variant", None) or "sting_marimba"
    if intro_mode == "jingle" and intro_variant:
        pitch = recommended_edge_tts_pitch_for_jingle(str(intro_variant))
    if pitch:
        config.edge_tts_pitch = pitch


def greeting_intro_path(config: Config, audio: IncomingCallAudioConfig) -> Optional[Path]:
    """
    Chemin WAV de l'intro musicale avant le message d'accueil.

    @param config Configuration.
    @param audio Bloc audio.
    @returns Path si intro active, sinon None.
    """
    mode = getattr(audio, "greeting_intro_mode", "none") or "none"
    if mode == "none":
        return None
    base = project_base(config)
    if mode == "wav":
        return resolve_intro_wav(base, audio.greeting_intro_wav_path)
    if mode == "track":
        configured = audio.greeting_intro_wav_path or str(WHISPERING_ICELAND_MP3)
        return resolve_intro_wav(base, configured)
    configured = audio.greeting_intro_wav_path or str(INTRO_DEFAULT_WAV)
    existing = resolve_intro_wav(base, configured)
    if existing:
        return existing
    variant = getattr(audio, "greeting_intro_variant", None) or "sting_marimba"
    variant_path = intro_variant_path(str(variant), base)
    default_path = base / INTRO_DEFAULT_WAV
    try:
        duration_ms = int(float(getattr(audio, "greeting_intro_sec", 3.2) or 3.2) * 1000)
        write_greeting_intro_wav(variant_path, variant=str(variant), duration_ms=duration_ms)
        write_greeting_intro_wav(default_path, variant=str(variant), duration_ms=duration_ms)
        return default_path if default_path.is_file() else variant_path
    except OSError as exc:
        logger.warning("greeting_intro: {}", exc)
        return None


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
    Cree les WAV par defaut (system/ + intros/default.wav).

    @param config Configuration (base_path).
    """
    base = project_base(config)
    try:
        ensure_voice_tree(base)
        beep = base / BEEP_WAV
        if not resolve_beep_wav(base):
            write_beep_wav_8k(beep)
        blocked = base / BLOCKED_WAV
        if not resolve_blocked_wav(base):
            write_beep_wav_8k(blocked, freq_hz=620, duration_ms=350)
        intro = base / INTRO_DEFAULT_WAV
        if not intro.is_file():
            write_greeting_intro_wav(intro, variant="sting_marimba", duration_ms=3200)
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
        base = project_base(config)
        found = resolve_beep_wav(base, audio.record_beep_wav_path)
        if found:
            return found
        ensure_default_voice_assets(config)
        return resolve_beep_wav(base, audio.record_beep_wav_path or str(BEEP_WAV))
    return None
