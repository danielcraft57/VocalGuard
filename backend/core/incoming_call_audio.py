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
    recommended_edge_tts_pitch_for_jingle,
    wav_matches_modem_profile,
    write_beep_wav_8k,
    write_greeting_intro_wav,
)
from backend.voice.modem_profile import resolve_profile_from_config
from backend.voice.musicscreen_jingles import (
    is_musicscreen_jingle,
    resolve_musicscreen_jingle,
)
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
    "Bonjour. Vous êtes bien chez Daniel Craft, de Loïc Daniel. "
    "Merci de laisser votre message après le bip."
)


def audio_float(value: object, default: float) -> float:
    """
    Convertit une valeur audio config en float (None / invalide -> default).

    @param value Valeur brute (str, int, float, None).
    @param default Fallback.
    @returns Float exploitable.
    """
    if value is None or value == "":
        return float(default)
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float(default)


def audio_int(value: object, default: int) -> int:
    """
    Convertit une valeur audio config en int (None / invalide -> default).

    @param value Valeur brute.
    @param default Fallback.
    @returns Entier exploitable.
    """
    if value is None or value == "":
        return int(default)
    try:
        return int(round(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return int(default)


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
    intro_variant = getattr(audio, "greeting_intro_variant", None) or "tesla"
    if intro_mode == "jingle" and intro_variant and not is_musicscreen_jingle(str(intro_variant)):
        pitch = recommended_edge_tts_pitch_for_jingle(str(intro_variant))
    if pitch:
        config.edge_tts_pitch = pitch
    gain = getattr(audio, "tts_voice_gain_db", None)
    if gain is not None:
        config.edge_tts_voice_gain_db = float(gain)


def resolve_intro_voice_bed_gain_db(
    audio: IncomingCallAudioConfig,
    intro_variant: str,
) -> Optional[float]:
    """
    Attenuation (dB negatif) de la musique sous la voix apres le fondu d'intro.

    Pour les jingles MusicScreen : le jingle continue sous l'annonce (pas de bed synthetique).
    0 ou proche de 0 = voix seule apres le fondu.

    @param audio Bloc audio settings.
    @param intro_variant Variante jingle active.
    @returns Gain en dB negatif, ou None si fond desactive.
    """
    bed_db = float(getattr(audio, "greeting_intro_voice_bed_db", -24.0) or -24.0)
    if bed_db > -1.0:
        return None
    return bed_db


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
        path = resolve_intro_wav(base, audio.greeting_intro_wav_path)
        if path and not wav_matches_modem_profile(path):
            try:
                write_greeting_intro_wav(path, variant="sting_marimba", duration_ms=3200)
            except OSError as exc:
                logger.warning("greeting_intro wav convert: {}", exc)
        return path
    if mode == "track":
        configured = audio.greeting_intro_wav_path or str(WHISPERING_ICELAND_MP3)
        return resolve_intro_wav(base, configured)
    if mode == "jingle":
        variant = getattr(audio, "greeting_intro_variant", None) or "tesla"
        return resolve_musicscreen_jingle(base, str(variant))
    configured = audio.greeting_intro_wav_path or str(INTRO_DEFAULT_WAV)
    return resolve_intro_wav(base, configured)


def blocked_message_text(settings: IncomingCallSettingsData) -> str:
    """
    Texte TTS pour appel bloque.

    @param settings Settings incoming_call.
    @returns Message bloque.
    """
    custom = (settings.audio.blocked_tts_text or "").strip()
    return custom or DEFAULT_BLOCKED_TTS


def refresh_modem_voice_assets(
    config: Config,
    settings: Optional[IncomingCallSettingsData] = None,
) -> list[str]:
    """
    Regenere beep, blocked_short et jingles intro au format modem actif (config VSM).

    @param config Configuration (base_path).
    @param settings Settings optionnels (variante intro active).
    @returns Chemins relatifs mis a jour.
    """
    base = project_base(config)
    ensure_voice_tree(base)
    updated: list[str] = []
    profile = resolve_profile_from_config(config)

    beep = base / BEEP_WAV
    write_beep_wav_8k(beep, profile=profile)
    updated.append(str(BEEP_WAV))

    blocked = base / BLOCKED_WAV
    write_beep_wav_8k(blocked, freq_hz=620, duration_ms=350, profile=profile)
    updated.append(str(BLOCKED_WAV))

    audio = settings.audio if settings else IncomingCallAudioConfig()
    variant = str(getattr(audio, "greeting_intro_variant", None) or "tesla")
    duration_ms = max(1500, int(float(getattr(audio, "greeting_intro_sec", 2.2) or 2.2) * 1000))

    ivr_beep = base / "ivr_wav" / "voicemail_beep.wav"
    ivr_beep.parent.mkdir(parents=True, exist_ok=True)
    write_beep_wav_8k(ivr_beep, profile=profile)
    updated.append("ivr_wav/voicemail_beep.wav")

    logger.info("Assets voix modem regeneres: {}", len(updated))
    return updated


def ensure_default_voice_assets(config: Config) -> None:
    """
    Cree ou met a jour les WAV par defaut (system/ + intros/default.wav).

    @param config Configuration (base_path).
    """
    try:
        refresh_modem_voice_assets(config)
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


def append_record_beep_to_modem_wav(
    config: Config,
    audio: IncomingCallAudioConfig,
    wav_path: Path,
    *,
    gap_ms: int = 500,
) -> None:
    """
    Colle le bip d'enregistrement a la fin du WAV accueil.

    @param config Configuration (base_path, profil modem).
    @param audio Bloc audio incoming_call.
    @param wav_path Fichier accueil modem a modifier sur place.
    @param gap_ms Silence entre message et bip (defaut 500 ms).
    """
    if audio.record_beep == "none" or not wav_path.is_file():
        return
    profile = resolve_profile_from_config(config)
    base = project_base(config)
    beep = beep_wav_path(config, audio)
    ivr_beep = base / "ivr_wav" / "voicemail_beep.wav"
    if not beep or not beep.is_file():
        ivr_beep.parent.mkdir(parents=True, exist_ok=True)
        if not ivr_beep.is_file():
            write_beep_wav_8k(ivr_beep, profile=profile)
        beep = ivr_beep
    if not beep.is_file():
        return
    from backend.voice.audio_utils import (
        export_wav_8k_8bit,
        load_audio_segment_modem,
        trim_leading_trailing_silence,
    )

    main = load_audio_segment_modem(wav_path)
    main = trim_leading_trailing_silence(main, padding_ms=0)
    beep_seg = load_audio_segment_modem(beep)
    beep_seg = trim_leading_trailing_silence(beep_seg, padding_ms=0)
    if gap_ms > 0:
        from pydub import AudioSegment

        gap = AudioSegment.silent(duration=gap_ms, frame_rate=profile.sample_rate)
        combined = main + gap + beep_seg
    else:
        combined = main + beep_seg
    tmp = wav_path.with_suffix(".beep.tmp.wav")
    export_wav_8k_8bit(combined, tmp, normalize=False, profile=profile)
    tmp.replace(wav_path)
