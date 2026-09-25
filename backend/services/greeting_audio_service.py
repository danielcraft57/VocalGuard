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
from backend.core.greeting_audiences import (
    ensure_audience_slots,
    greeting_text_for_audience,
    normalize_audience,
    resolve_audio_for_audience,
)
from backend.core.incoming_call_audio import (
    append_record_beep_to_modem_wav,
    audio_float,
    audio_int,
    beep_wav_path,
    greeting_intro_path,
    greeting_text,
    resolve_intro_voice_bed_gain_db,
    sync_edge_tts_from_audio,
)
from backend.core.incoming_call_settings import (
    _deep_merge_dict,
    apply_incoming_call_settings,
    load_incoming_call_settings,
)
from backend.core.incoming_call_types import (
    GreetingAudienceKey,
    IncomingCallAudioConfig,
    IncomingCallSettingsData,
)
from backend.voice.audio_utils import (
    combine_intro_voice_crossfade,
    combine_music_track_voice_overlay,
    default_bed_variant_for_jingle,
    export_listen_preview_wav,
    export_raw_listen_preview,
    tts_source_to_modem_wav,
)
from backend.voice.musicscreen_jingles import is_musicscreen_jingle
from backend.voice.modem_profile import USR_VOICE_PROFILE, resolve_profile_from_config
from backend.voice.node15_voice_client import Node15VoiceClient
from backend.voice.synthesis import VoiceSynthesis
from backend.voice.tts_url import resolve_tts_service_url, resolve_tts_token

if TYPE_CHECKING:
    from backend.core.call_manager import CallManager

GREETING_MODEM_ACTIVE_BASENAME = "greeting_modem_active"


def greeting_modem_active_wav_path(
    config: Config,
    audience: Optional[str] = None,
) -> Path:
    """
    Chemin du WAV accueil pret pour le modem (mix final 8 kHz).

    @param config Configuration (base_path).
    @param audience Slot known/unknown/commercial (None = unknown legacy).
    @returns Fichier sous ivr_wav/.
    """
    base = Path(config.base_path) if config.base_path else Path.cwd()
    key = normalize_audience(audience)
    if key == "unknown":
        return base / "ivr_wav" / f"{GREETING_MODEM_ACTIVE_BASENAME}.wav"
    return base / "ivr_wav" / f"{GREETING_MODEM_ACTIVE_BASENAME}_{key}.wav"


def greeting_modem_active_meta_path(
    config: Config,
    audience: Optional[str] = None,
) -> Path:
    """
    Metadonnees du cache accueil modem actif.

    @param config Configuration.
    @param audience Slot audience.
    @returns Fichier JSON a cote du WAV actif.
    """
    return greeting_modem_active_wav_path(config, audience).with_suffix(".meta.json")


def greeting_settings_signature(
    settings: IncomingCallSettingsData,
    greeting: str,
    config: Optional[Config] = None,
    audience: Optional[str] = None,
) -> str:
    """
    Empreinte des parametres qui influencent le mix accueil modem.

    @param settings Settings incoming_call effectifs.
    @param greeting Texte accueil TTS.
    @param config Configuration modem.
    @param audience Slot audience.
    @returns Hash court stable.
    """
    profile = resolve_profile_from_config(config) if config is not None else USR_VOICE_PROFILE
    payload = {
        "audience": normalize_audience(audience),
        "greeting": " ".join((greeting or "").split()),
        "audio": settings.audio.model_dump(),
        "modem_audio": {
            "rate": profile.sample_rate,
            "width": profile.sample_width,
        },
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def is_greeting_modem_active_fresh(
    config: Config,
    settings: IncomingCallSettingsData,
    greeting: str,
    audience: Optional[str] = None,
) -> bool:
    """
    True si le WAV accueil modem correspond aux settings courants.

    @param config Configuration.
    @param settings Settings effectifs.
    @param greeting Texte accueil.
    @param audience Slot audience.
    @returns Etat fraicheur du cache actif.
    """
    key = normalize_audience(audience)
    wav = greeting_modem_active_wav_path(config, key)
    meta = greeting_modem_active_meta_path(config, key)
    if not wav.is_file() or wav.stat().st_size < 2000 or not meta.is_file():
        return False
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        return data.get("signature") == greeting_settings_signature(
            settings, greeting, config, key
        )
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def _write_greeting_modem_active_meta(
    config: Config,
    settings: IncomingCallSettingsData,
    greeting: str,
    audience: Optional[str] = None,
) -> str:
    """
    Persiste la signature du WAV accueil modem actif.

    @param config Configuration.
    @param settings Settings utilises pour la generation.
    @param greeting Texte accueil.
    @param audience Slot audience.
    @returns Horodatage ISO UTC ecrit dans le meta.
    """
    key = normalize_audience(audience)
    regenerated_at = datetime.now(timezone.utc).isoformat()
    greeting_modem_active_meta_path(config, key).write_text(
        json.dumps(
            {
                "audience": key,
                "signature": greeting_settings_signature(settings, greeting, config, key),
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

    Merge profond (notamment ``audiences``) pour ne pas ecraser les slots
    par un patch partiel.

    @param settings Settings charges.
    @param audio_override Patch audio optionnel (formulaire UI).
    @returns Copie avec audio fusionne.
    """
    if not audio_override:
        ensure_audience_slots(settings.audio)
        return settings
    merged = settings.model_copy(deep=True)
    merged.audio = IncomingCallAudioConfig.model_validate(
        _deep_merge_dict(merged.audio.model_dump(), dict(audio_override))
    )
    ensure_audience_slots(merged.audio)
    return merged


def _prepare_audience_settings(
    config: Config,
    *,
    audio_override: Optional[dict[str, Any]] = None,
    audience: Optional[str] = None,
) -> tuple[IncomingCallSettingsData, GreetingAudienceKey, str]:
    """
    Charge, fusionne et resout les settings pour une audience.

    @param config Configuration.
    @param audio_override Patch UI.
    @param audience Cle audience.
    @returns (settings resolus, audience, texte greeting).
    """
    key = normalize_audience(audience)
    base = _merge_audio_settings(load_incoming_call_settings(config), audio_override)
    ensure_audience_slots(base.audio)
    resolved = resolve_audio_for_audience(base, key)
    apply_incoming_call_settings(config, resolved)
    sync_edge_tts_from_audio(config, resolved.audio)
    greeting = greeting_text_for_audience(config, base, key)
    return resolved, key, greeting


async def _synthesize_voice_modem_wav(
    config: Config,
    synthesis: VoiceSynthesis,
    greeting: str,
    *,
    audience: Optional[str] = None,
    audio: Optional[IncomingCallAudioConfig] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """
    Genere le WAV voix seul (modem 8 kHz) pour apercu ou cache modem.

    Passe par ElevenLabs si ``tts_provider=elevenlabs``, sinon
    Edge TTS local (``synthesis.speak``), puis conversion modem.

    @param config Configuration.
    @param synthesis Moteur TTS initialise (Edge).
    @param greeting Texte accueil.
    @param audience Slot (fichier temp separe par audience).
    @param audio Bloc audio resolu (provider / voice id).
    @param out_path Destination WAV modem (defaut: preview temporaire).
    @returns Chemin WAV modem.
    @raises RuntimeError Si generation impossible.
    """
    base = Path(config.base_path) if config.base_path else Path.cwd()
    key = normalize_audience(audience)
    out = Path(out_path) if out_path is not None else (
        base / "data" / "audio_previews" / f"_preview_voice_{key}.wav"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    provider = str(getattr(audio, "tts_provider", None) or "edge").strip().lower()
    if provider == "elevenlabs":
        from backend.voice.elevenlabs_client import (
            resolve_elevenlabs_api_key,
            resolve_elevenlabs_default_voice_id,
            resolve_elevenlabs_model_id,
            synthesize_elevenlabs_mp3,
        )

        api_key = resolve_elevenlabs_api_key(config)
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY manquante")
        voice_id = str(
            getattr(audio, "elevenlabs_voice_id", None)
            or resolve_elevenlabs_default_voice_id(config)
        )
        mp3_path = base / "data" / "audio_previews" / f"_preview_voice_{key}_el.mp3"
        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda api_key=api_key, greeting=greeting, voice_id=voice_id, mp3_path=mp3_path, config=config: synthesize_elevenlabs_mp3(
                api_key=api_key,
                text=greeting,
                voice_id=voice_id,
                model_id=resolve_elevenlabs_model_id(config),
                out_path=mp3_path,
            ),
        )
        temp = mp3_path
    else:
        temp = await synthesis.speak(
            greeting,
            rate=getattr(config, "edge_tts_rate", "+0%"),
            pitch=getattr(config, "edge_tts_pitch", "+0Hz"),
        )
        if not temp or not Path(temp).exists():
            raise RuntimeError("Synthese TTS accueil echouee")

    tts_source_to_modem_wav(
        Path(temp),
        out,
        profile=resolve_profile_from_config(config),
        voice_gain_db=audio_float(getattr(config, "edge_tts_voice_gain_db", None), -6.0),
    )
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
    profile = resolve_profile_from_config(config)
    intro = greeting_intro_path(config, audio)
    intro_mode = str(getattr(audio, "greeting_intro_mode", "none") or "none")

    if intro_mode == "track" and intro and intro.is_file():
        intro_ms = audio_int(
            audio_float(getattr(audio, "greeting_intro_sec", None), 0.0) * 1000,
            0,
        )
        crossfade_ms = audio_int(getattr(audio, "greeting_intro_crossfade_ms", None), 450)
        music_offset_ms = audio_int(
            audio_float(getattr(audio, "greeting_intro_music_offset_sec", None), 0.0) * 1000,
            0,
        )
        track_duck_db = audio_float(getattr(audio, "greeting_intro_track_duck_db", None), 0.0)
        voice_gain = audio_float(getattr(audio, "greeting_intro_voice_gain_db", None), 0.0)
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
        append_record_beep_to_modem_wav(config, audio, out_modem)
        return

    if intro_mode in ("jingle", "wav") and intro and intro.is_file():
        intro_ms = audio_int(
            audio_float(getattr(audio, "greeting_intro_sec", None), 2.2) * 1000,
            2200,
        )
        crossfade_ms = audio_int(getattr(audio, "greeting_intro_crossfade_ms", None), 280)
        intro_variant = str(getattr(audio, "greeting_intro_variant", "tesla") or "tesla")
        bed_db = resolve_intro_voice_bed_gain_db(audio, intro_variant)
        voice_gain = audio_float(getattr(audio, "greeting_intro_voice_gain_db", None), 0.0)
        bed_variant = getattr(audio, "greeting_intro_bed_variant", None)
        if bed_variant is None and not is_musicscreen_jingle(intro_variant):
            bed_variant = default_bed_variant_for_jingle(intro_variant)
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
            profile=profile,
        )
        append_record_beep_to_modem_wav(config, audio, out_modem)
        return

    import shutil

    shutil.copy2(voice_wav, out_modem)

    append_record_beep_to_modem_wav(config, audio, out_modem)


def _build_intro_listen_preview_sync(
    config: Config,
    settings: IncomingCallSettingsData,
    *,
    out_base: Path,
) -> Path:
    """
    Apercu intro avec les reglages de duree / offset appliques.

    Coupe le fichier a ``greeting_intro_sec`` (moment ou la voix prend le
    relais). Les volumes voix/jingle se valident via « Mix complet ».

    @param config Configuration.
    @param settings Settings effectifs.
    @param out_base Chemin de sortie sans extension.
    @returns Fichier audio (.wav).
    @raises RuntimeError Si intro absente.
    """
    from pydub import AudioSegment

    audio = settings.audio
    intro_mode = str(getattr(audio, "greeting_intro_mode", "none") or "none")
    if intro_mode == "none":
        raise RuntimeError("Aucune intro configuree")
    intro = greeting_intro_path(config, audio)
    if not intro or not intro.is_file():
        raise RuntimeError("Intro musicale indisponible")

    default_sec = 0.0 if intro_mode == "track" else 2.2
    intro_sec = audio_float(getattr(audio, "greeting_intro_sec", None), default_sec)
    offset_sec = audio_float(getattr(audio, "greeting_intro_music_offset_sec", None), 0.0)

    segment = AudioSegment.from_file(str(intro))
    if intro_mode == "track" and offset_sec > 0:
        start_ms = min(len(segment), int(offset_sec * 1000))
        segment = segment[start_ms:]

    # Duree solo avant la voix (= placement voix).
    if intro_sec <= 0:
        # 0 = voix des le debut : petit extrait pour confirmer le point de depart.
        cut_ms = min(len(segment), 400)
    else:
        cut_ms = min(len(segment), max(80, int(intro_sec * 1000)))
    segment = segment[:cut_ms]

    out_path = out_base.with_suffix(".wav")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    segment.export(str(out_path), format="wav")
    return out_path


async def try_remote_greeting_mix(
    config: Config,
    settings: IncomingCallSettingsData,
    greeting: str,
    *,
    out_path: Path,
    output: str = "modem",
) -> Optional[Path]:
    """
    Demande a node15 le TTS + mix accueil si ``TTS_SERVICE_URL`` est configure.

    Upload l'intro / bip locaux, recupere le WAV mixe.

    @param config Configuration.
    @param settings Settings audio effectifs.
    @param greeting Texte accueil.
    @param out_path Destination locale du WAV.
    @param output modem | listen | voice.
    @returns ``out_path`` si OK, sinon None (repli local).
    """
    base_url = resolve_tts_service_url(config)
    if not base_url:
        return None
    audio = settings.audio
    profile = resolve_profile_from_config(config)
    intro_mode = str(getattr(audio, "greeting_intro_mode", "none") or "none")
    intro = greeting_intro_path(config, audio) if intro_mode != "none" else None
    append_beep = output == "modem" and str(getattr(audio, "record_beep", "wav") or "wav") != "none"
    beep = beep_wav_path(config, audio) if append_beep else None
    bed_variant = getattr(audio, "greeting_intro_bed_variant", None)
    client = Node15VoiceClient(
        base_url,
        token=resolve_tts_token(config),
        timeout_sec=180.0,
    )
    try:
        payload = await client.greeting_mix(
            greeting,
            voice=str(getattr(audio, "edge_tts_voice", None) or getattr(config, "edge_tts_voice", None) or "fr-FR-DeniseNeural"),
            rate=str(getattr(audio, "edge_tts_rate", None) or getattr(config, "edge_tts_rate", None) or "+0%"),
            pitch=str(getattr(audio, "edge_tts_pitch", None) or getattr(config, "edge_tts_pitch", None) or "+0Hz"),
            tts_voice_gain_db=float(
                getattr(audio, "tts_voice_gain_db", None)
                or getattr(config, "edge_tts_voice_gain_db", -6.0)
                or -6.0
            ),
            intro_mode=intro_mode,
            intro_variant=str(getattr(audio, "greeting_intro_variant", "tesla") or "tesla"),
            intro_sec=audio_float(getattr(audio, "greeting_intro_sec", None), 2.2),
            crossfade_ms=audio_int(getattr(audio, "greeting_intro_crossfade_ms", None), 380),
            voice_bed_db=audio_float(getattr(audio, "greeting_intro_voice_bed_db", None), -18.0),
            voice_mix_gain_db=audio_float(getattr(audio, "greeting_intro_voice_gain_db", None), 0.0),
            track_duck_db=audio_float(getattr(audio, "greeting_intro_track_duck_db", None), 0.0),
            music_offset_sec=audio_float(getattr(audio, "greeting_intro_music_offset_sec", None), 0.0),
            bed_variant=str(bed_variant) if bed_variant else None,
            sample_rate=int(profile.sample_rate),
            sample_width=int(profile.sample_width),
            append_beep=append_beep,
            output=output,
            intro_path=intro if intro and intro.is_file() else None,
            beep_path=beep if beep and beep.is_file() else None,
        )
    except Exception as exc:
        logger.warning("greeting-mix distant KO ({}), repli local: {}", base_url, exc)
        return None
    if not payload or len(payload) < 200:
        logger.warning("greeting-mix distant: payload trop court")
        return None
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(payload)
    logger.info(
        "Accueil mixe via node15 ({} octets, output={})",
        len(payload),
        output,
    )
    return out_path


async def build_greeting_listen_preview(
    config: Config,
    *,
    audio_override: Optional[dict[str, Any]] = None,
    preview_mode: str = "full",
    audience: Optional[str] = None,
) -> Path:
    """
    Genere un WAV ecoute PC (44.1 kHz) de l'accueil selon les parametres.

    Preferre ``TTS_SERVICE_URL`` /greeting-mix (TTS+mix sur node15), sinon local.

    @param config Configuration projet.
    @param audio_override Patch audio UI (non sauvegarde).
    @param preview_mode full | voice | intro.
    @param audience known | unknown | commercial.
    @returns Chemin WAV ecoute.
    @raises RuntimeError Si la generation echoue.
    """
    settings, key, greeting = _prepare_audience_settings(
        config,
        audio_override=audio_override,
        audience=audience,
    )

    synthesis = VoiceSynthesis(config)
    await synthesis.initialize()

    base = Path(config.base_path) if config.base_path else Path.cwd()
    preview_dir = base / "data" / "audio_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    modem_tmp = preview_dir / f"_preview_modem_{key}.wav"
    listen_base = preview_dir / f"greeting_listen_preview_{key}"
    listen_out = listen_base.with_suffix(".wav")
    loop = asyncio.get_running_loop()

    mode = (preview_mode or "full").strip().lower()
    if mode == "intro":
        return await loop.run_in_executor(
            None,
            lambda: _build_intro_listen_preview_sync(
                config,
                settings,
                out_base=listen_base,
            ),
        )

    remote_output = "voice" if mode == "voice" else "listen"
    provider = str(getattr(settings.audio, "tts_provider", None) or "edge").strip().lower()
    # node15 /greeting-mix = Edge TTS seulement — ElevenLabs reste local.
    remote = None
    if provider != "elevenlabs":
        remote = await try_remote_greeting_mix(
            config,
            settings,
            greeting,
            out_path=listen_out,
            output=remote_output,
        )
    if remote is not None:
        return remote

    if mode == "voice":
        voice_wav = await _synthesize_voice_modem_wav(
            config, synthesis, greeting, audience=key, audio=settings.audio
        )
        export_listen_preview_wav(voice_wav, listen_out, target_peak=None)
        return listen_out

    voice_wav = await _synthesize_voice_modem_wav(
        config, synthesis, greeting, audience=key, audio=settings.audio
    )
    await loop.run_in_executor(
        None,
        lambda: _build_modem_greeting_wav_sync(
            config,
            settings,
            voice_wav,
            out_modem=modem_tmp,
        ),
    )
    export_listen_preview_wav(modem_tmp, listen_out, target_peak=None)
    return listen_out


async def regenerate_greeting_production_cache(
    config: Config,
    call_manager: Optional["CallManager"] = None,
    *,
    audio_override: Optional[dict[str, Any]] = None,
    audience: Optional[str] = None,
) -> dict[str, Any]:
    """
    Supprime et regenere le cache accueil utilise par le modem.

    @param config Configuration.
    @param call_manager CallManager telephonie (requis en prod).
    @param audio_override Patch audio UI (meme logique que l'apercu).
    @param audience Slot known/unknown/commercial.
    @returns Metadonnees du cache genere.
    @raises RuntimeError Si regeneration impossible.
    """
    if call_manager is None:
        raise RuntimeError("Regeneration accueil indisponible sans daemon telephonie")
    return await call_manager.regenerate_greeting_cache(
        audio_override=audio_override,
        audience=audience,
    )


async def get_greeting_cache_status(
    config: Config,
    call_manager: Optional["CallManager"] = None,
    *,
    audience: Optional[str] = None,
) -> dict[str, Any]:
    """
    Retourne l'etat du cache accueil pour une audience.

    @param config Configuration.
    @param call_manager CallManager optionnel.
    @param audience Slot audience.
    @returns Snapshot cache (fichiers, duree, voix).
    """
    key = normalize_audience(audience)
    settings = load_incoming_call_settings(config)
    ensure_audience_slots(settings.audio)
    resolved = resolve_audio_for_audience(settings, key)
    apply_incoming_call_settings(config, resolved)
    greeting = greeting_text_for_audience(config, settings, key)
    active = greeting_modem_active_wav_path(config, key)
    if call_manager is not None and key == "unknown":
        early = call_manager._resolve_early_greeting_wav_path()
        if early and early.is_file():
            active = early
    base = Path(config.base_path) if config.base_path else Path.cwd()
    voice_wav = base / "ivr_wav" / f"voicemail_greeting_{key}.wav"
    if not voice_wav.is_file():
        voice_wav = base / "ivr_wav" / "voicemail_greeting.wav"
    regenerated_at = None
    meta = greeting_modem_active_meta_path(config, key)
    if meta.is_file():
        try:
            regenerated_at = json.loads(meta.read_text(encoding="utf-8")).get("regenerated_at")
        except (OSError, json.JSONDecodeError):
            regenerated_at = None
    return {
        "audience": key,
        "track_wav": active.name if active.is_file() else None,
        "voice_wav": voice_wav.name if voice_wav.is_file() else None,
        "duration_sec": _wav_duration_sec(active) if active.is_file() else None,
        "voice": getattr(config, "edge_tts_voice", "") or "",
        "pitch": getattr(config, "edge_tts_pitch", "") or "",
        "rate": getattr(config, "edge_tts_rate", "") or "",
        "text": greeting,
        "regenerated_at": regenerated_at,
    }
