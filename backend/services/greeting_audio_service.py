"""
Generation d'apercu et regeneration du cache accueil (TTS + mix musical).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from loguru import logger

from backend.core.config import Config
from backend.core.incoming_call_audio import (
    greeting_intro_path,
    greeting_text,
    sync_edge_tts_from_audio,
)
from backend.core.incoming_call_settings import (
    apply_incoming_call_settings,
    load_incoming_call_settings,
)
from backend.core.incoming_call_types import IncomingCallAudioConfig, IncomingCallSettingsData
from backend.voice.audio_utils import (
    combine_intro_voice_crossfade,
    combine_music_track_voice_overlay,
    default_bed_variant_for_jingle,
    export_listen_preview_wav,
    tts_source_to_modem_wav,
)
from backend.voice.ivr_cache import IvrAudioCache
from backend.voice.synthesis import VoiceSynthesis

if TYPE_CHECKING:
    from backend.core.call_manager import CallManager

GREETING_MODEM_ACTIVE_BASENAME = "greeting_modem_active"


def greeting_modem_active_wav_path(config: Config) -> Path:
    """
    Chemin du WAV accueil pret pour le modem (mix final 8 kHz).

    @param config Configuration (base_path).
    @returns Fichier sous ivr_wav/.
    """
    base = Path(config.base_path) if config.base_path else Path.cwd()
    return base / "ivr_wav" / f"{GREETING_MODEM_ACTIVE_BASENAME}.wav"


def greeting_modem_active_meta_path(config: Config) -> Path:
    """
    Metadonnees du cache accueil modem actif.

    @param config Configuration.
    @returns Fichier JSON a cote du WAV actif.
    """
    return greeting_modem_active_wav_path(config).with_suffix(".meta.json")


def greeting_settings_signature(
    settings: IncomingCallSettingsData,
    greeting: str,
) -> str:
    """
    Empreinte des parametres qui influencent le mix accueil modem.

    @param settings Settings incoming_call effectifs.
    @param greeting Texte accueil TTS.
    @returns Hash court stable.
    """
    payload = {
        "greeting": " ".join((greeting or "").split()),
        "audio": settings.audio.model_dump(),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def is_greeting_modem_active_fresh(
    config: Config,
    settings: IncomingCallSettingsData,
    greeting: str,
) -> bool:
    """
    True si greeting_modem_active.wav correspond aux settings courants.

    @param config Configuration.
    @param settings Settings effectifs.
    @param greeting Texte accueil.
    @returns Etat fraicheur du cache actif.
    """
    wav = greeting_modem_active_wav_path(config)
    meta = greeting_modem_active_meta_path(config)
    if not wav.is_file() or wav.stat().st_size < 2000 or not meta.is_file():
        return False
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        return data.get("signature") == greeting_settings_signature(settings, greeting)
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def _write_greeting_modem_active_meta(
    config: Config,
    settings: IncomingCallSettingsData,
    greeting: str,
) -> str:
    """
    Persiste la signature du WAV accueil modem actif.

    @param config Configuration.
    @param settings Settings utilises pour la generation.
    @param greeting Texte accueil.
    @returns Horodatage ISO UTC ecrit dans le meta.
    """
    regenerated_at = datetime.now(timezone.utc).isoformat()
    greeting_modem_active_meta_path(config).write_text(
        json.dumps(
            {
                "signature": greeting_settings_signature(settings, greeting),
                "text": greeting,
                "regenerated_at": regenerated_at,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return regenerated_at


def _wav_duration_sec(path: Path) -> Optional[float]:
    """
    Duree d'un fichier WAV en secondes.

    @param path Fichier WAV.
    @returns Duree ou None si illisible.
    """
    try:
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate()
            if rate <= 0:
                return None
            return round(wf.getnframes() / float(rate), 2)
    except (OSError, wave.Error):
        return None


def _merge_audio_settings(
    settings: IncomingCallSettingsData,
    audio_override: Optional[dict[str, Any]],
) -> IncomingCallSettingsData:
    """
    Fusionne un patch audio partiel dans les settings.

    @param settings Settings charges.
    @param audio_override Patch audio optionnel (formulaire UI).
    @returns Copie avec audio fusionne.
    """
    if not audio_override:
        return settings
    merged = settings.model_copy(deep=True)
    merged.audio = IncomingCallAudioConfig.model_validate(
        {**merged.audio.model_dump(), **audio_override}
    )
    return merged


async def _synthesize_voice_modem_wav(
    config: Config,
    synthesis: VoiceSynthesis,
    greeting: str,
) -> Path:
    """
    Genere le WAV voix seul (modem 8 kHz) pour apercu.

    @param config Configuration.
    @param synthesis Moteur TTS initialise.
    @param greeting Texte accueil.
    @returns Chemin WAV modem.
    @raises RuntimeError Si generation impossible.
    """
    temp = await synthesis.speak(
        greeting,
        rate=getattr(config, "edge_tts_rate", "+0%"),
        pitch=getattr(config, "edge_tts_pitch", "+0Hz"),
    )
    if not temp or not Path(temp).exists():
        raise RuntimeError("Synthese TTS accueil echouee")
    base = Path(config.base_path) if config.base_path else Path.cwd()
    out = base / "data" / "audio_previews" / "_preview_voice.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    tts_source_to_modem_wav(Path(temp), out)
    return out


def _build_modem_greeting_wav_sync(
    config: Config,
    settings: IncomingCallSettingsData,
    voice_wav: Path,
    *,
    out_modem: Path,
) -> None:
    """
    Construit le WAV modem final (mix intro + voix selon le mode).

    @param config Configuration.
    @param settings Settings effectifs.
    @param voice_wav Voix TTS modem.
    @param out_modem Fichier de sortie modem 8 kHz.
    """
    audio = settings.audio
    intro = greeting_intro_path(config, audio)
    intro_mode = str(getattr(audio, "greeting_intro_mode", "none") or "none")

    if intro_mode == "track" and intro and intro.is_file():
        intro_ms = int(float(getattr(audio, "greeting_intro_sec", 0.0) or 0.0) * 1000)
        crossfade_ms = int(float(getattr(audio, "greeting_intro_crossfade_ms", 450) or 450))
        music_offset_ms = int(
            float(getattr(audio, "greeting_intro_music_offset_sec", 0.0) or 0.0) * 1000
        )
        track_duck_db = float(getattr(audio, "greeting_intro_track_duck_db", 0.0) or 0.0)
        voice_gain = float(getattr(audio, "greeting_intro_voice_gain_db", 0.0) or 0.0)
        combine_music_track_voice_overlay(
            intro,
            voice_wav,
            out_modem,
            music_solo_ms=intro_ms,
            music_offset_ms=music_offset_ms,
            voice_fade_ms=crossfade_ms,
            music_duck_db=track_duck_db if track_duck_db > 0.5 else None,
            voice_mix_gain_db=voice_gain,
        )
        return

    if intro_mode in ("jingle", "wav") and intro and intro.is_file():
        intro_ms = int(float(getattr(audio, "greeting_intro_sec", 2.2) or 2.2) * 1000)
        crossfade_ms = int(float(getattr(audio, "greeting_intro_crossfade_ms", 280) or 280))
        bed_db = float(getattr(audio, "greeting_intro_voice_bed_db", -24.0) or -24.0)
        if bed_db > -1.0:
            bed_db = None
        voice_gain = float(getattr(audio, "greeting_intro_voice_gain_db", 0.0) or 0.0)
        intro_variant = str(getattr(audio, "greeting_intro_variant", "sting_marimba") or "sting_marimba")
        bed_variant = (
            getattr(audio, "greeting_intro_bed_variant", None)
            or default_bed_variant_for_jingle(intro_variant)
        )
        combine_intro_voice_crossfade(
            intro,
            voice_wav,
            out_modem,
            crossfade_ms=crossfade_ms,
            intro_max_ms=intro_ms,
            intro_variant=intro_variant,
            normalize=True,
            voice_bed_gain_db=bed_db,
            voice_mix_gain_db=voice_gain,
            voice_bed_variant=str(bed_variant),
        )
        return

    import shutil

    shutil.copy2(voice_wav, out_modem)


async def build_greeting_listen_preview(
    config: Config,
    *,
    audio_override: Optional[dict[str, Any]] = None,
) -> Path:
    """
    Genere un WAV ecoute PC (44.1 kHz) de l'accueil selon les parametres.

    @param config Configuration projet.
    @param audio_override Patch audio UI (non sauvegarde).
    @returns Chemin WAV ecoute.
    @raises RuntimeError Si la generation echoue.
    """
    settings = _merge_audio_settings(load_incoming_call_settings(config), audio_override)
    apply_incoming_call_settings(config, settings)
    sync_edge_tts_from_audio(config, settings.audio)

    synthesis = VoiceSynthesis(config)
    await synthesis.initialize()
    greeting = greeting_text(config, settings)

    base = Path(config.base_path) if config.base_path else Path.cwd()
    preview_dir = base / "data" / "audio_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    modem_tmp = preview_dir / "_preview_modem.wav"
    listen_out = preview_dir / "greeting_listen_preview.wav"

    voice_wav = await _synthesize_voice_modem_wav(config, synthesis, greeting)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: _build_modem_greeting_wav_sync(
            config,
            settings,
            voice_wav,
            out_modem=modem_tmp,
        ),
    )
    export_listen_preview_wav(modem_tmp, listen_out)
    return listen_out


async def regenerate_greeting_production_cache(
    config: Config,
    call_manager: Optional["CallManager"] = None,
    *,
    audio_override: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Supprime et regenere le cache accueil utilise par le modem.

    @param config Configuration.
    @param call_manager CallManager telephonie (requis en prod).
    @param audio_override Patch audio UI (meme logique que l'apercu).
    @returns Metadonnees du cache genere.
    @raises RuntimeError Si regeneration impossible.
    """
    if call_manager is None:
        raise RuntimeError("Regeneration accueil indisponible sans daemon telephonie")
    return await call_manager.regenerate_greeting_cache(audio_override=audio_override)


async def get_greeting_cache_status(
    config: Config,
    call_manager: Optional["CallManager"] = None,
) -> dict[str, Any]:
    """
    Retourne l'etat du cache accueil actuellement configure.

    @param config Configuration.
    @param call_manager CallManager optionnel.
    @returns Snapshot cache (fichiers, duree, voix).
    """
    settings = load_incoming_call_settings(config)
    apply_incoming_call_settings(config, settings)
    greeting = greeting_text(config, settings)
    active = greeting_modem_active_wav_path(config)
    if call_manager is not None:
        resolved = call_manager._resolve_early_greeting_wav_path()
        if resolved and resolved.is_file():
            active = resolved
    base = Path(config.base_path) if config.base_path else Path.cwd()
    voice_wav = base / "ivr_wav" / "voicemail_greeting.wav"
    regenerated_at = None
    meta = greeting_modem_active_meta_path(config)
    if meta.is_file():
        try:
            regenerated_at = json.loads(meta.read_text(encoding="utf-8")).get("regenerated_at")
        except (OSError, json.JSONDecodeError):
            regenerated_at = None
    return {
        "track_wav": active.name if active.is_file() else None,
        "voice_wav": voice_wav.name if voice_wav.is_file() else None,
        "duration_sec": _wav_duration_sec(active) if active.is_file() else None,
        "voice": getattr(config, "edge_tts_voice", "") or "",
        "pitch": getattr(config, "edge_tts_pitch", "") or "",
        "rate": getattr(config, "edge_tts_rate", "") or "",
        "text": greeting,
        "regenerated_at": regenerated_at,
    }
