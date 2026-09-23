"""
Accueils multi-profils : connus / inconnus / commerciaux.

Mappe les audiences produit vers les profils runtime permitted/screened/blocked
et resout un bloc audio effectif par slot.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, Optional

from backend.core.config import Config
from backend.core.incoming_call_types import (
    GreetingAudienceAudio,
    GreetingAudienceKey,
    IncomingCallAudioConfig,
    IncomingCallSettingsData,
    IncomingProfileName,
)

GREETING_AUDIENCE_KEYS: tuple[GreetingAudienceKey, ...] = ("known", "unknown", "commercial")

DEFAULT_AUDIENCE_TEXTS: Dict[GreetingAudienceKey, str] = {
    "known": (
        "Bonjour. Vous etes bien chez Daniel Craft, de Loic Daniel. "
        "Merci de laisser votre message apres le bip."
    ),
    "unknown": (
        "Bonjour, je ne connais pas votre numero ! "
        "Merci de vous presenter et de laisser vos coordonnees."
    ),
    "commercial": (
        "Desole, cet appel ne peut pas aboutir. "
        "Merci de ne pas rappeler pour du demarchage."
    ),
}

_AUDIENCE_OVERRIDE_FIELDS: tuple[str, ...] = (
    "greeting_source",
    "greeting_wav_path",
    "greeting_tts_text",
    "tts_provider",
    "elevenlabs_voice_id",
    "edge_tts_rate",
    "edge_tts_voice",
    "edge_tts_pitch",
    "tts_voice_gain_db",
    "greeting_intro_mode",
    "greeting_intro_variant",
    "greeting_intro_wav_path",
    "greeting_intro_sec",
    "greeting_intro_crossfade_ms",
    "greeting_intro_voice_gain_db",
    "greeting_intro_voice_bed_db",
    "greeting_intro_bed_variant",
    "greeting_intro_track_duck_db",
    "greeting_intro_music_offset_sec",
)


def normalize_audience(raw: Optional[str]) -> GreetingAudienceKey:
    """
    Normalise une cle audience (defaut: unknown).

    @param raw Valeur libre (query/body).
    @returns Cle audience valide.
    """
    key = (raw or "unknown").strip().lower()
    if key in GREETING_AUDIENCE_KEYS:
        return key  # type: ignore[return-value]
    aliases = {
        "permitted": "known",
        "whitelist": "known",
        "connu": "known",
        "connus": "known",
        "screened": "unknown",
        "inconnu": "unknown",
        "inconnus": "unknown",
        "blocked": "commercial",
        "spam": "commercial",
        "commerciaux": "commercial",
    }
    mapped = aliases.get(key)
    if mapped in GREETING_AUDIENCE_KEYS:
        return mapped  # type: ignore[return-value]
    return "unknown"


def audience_from_profile(profile: IncomingProfileName) -> GreetingAudienceKey:
    """
    Mappe un profil runtime vers l'audience produit.

    @param profile permitted | screened | blocked.
    @returns known | unknown | commercial.
    """
    if profile == "permitted":
        return "known"
    if profile == "blocked":
        return "commercial"
    return "unknown"


def profile_from_audience(audience: GreetingAudienceKey) -> IncomingProfileName:
    """
    Mappe une audience produit vers le profil runtime.

    @param audience known | unknown | commercial.
    @returns permitted | screened | blocked.
    """
    if audience == "known":
        return "permitted"
    if audience == "commercial":
        return "blocked"
    return "screened"


def default_audience_slot(
    audience: GreetingAudienceKey,
    base: Optional[IncomingCallAudioConfig] = None,
) -> GreetingAudienceAudio:
    """
    Construit un slot audience avec texte par defaut.

    @param audience Cle produit.
    @param base Audio global (voix/intro heritees si present).
    @returns Slot peuplé.
    """
    text = DEFAULT_AUDIENCE_TEXTS[audience]
    if base is not None and audience == "unknown":
        custom = (base.greeting_tts_text or "").strip()
        if custom:
            text = custom
    if base is not None and audience == "commercial":
        blocked = (base.blocked_tts_text or "").strip()
        if blocked:
            text = blocked
    slot = GreetingAudienceAudio(
        greeting_source="tts",
        greeting_tts_text=text,
    )
    if base is not None:
        slot.edge_tts_voice = base.edge_tts_voice
        slot.edge_tts_rate = base.edge_tts_rate
        slot.edge_tts_pitch = base.edge_tts_pitch
        slot.tts_voice_gain_db = base.tts_voice_gain_db
        slot.greeting_intro_mode = base.greeting_intro_mode
        slot.greeting_intro_variant = base.greeting_intro_variant
        slot.greeting_intro_wav_path = base.greeting_intro_wav_path
        slot.greeting_intro_sec = base.greeting_intro_sec
        slot.greeting_intro_crossfade_ms = base.greeting_intro_crossfade_ms
        slot.greeting_intro_voice_gain_db = base.greeting_intro_voice_gain_db
        slot.greeting_intro_voice_bed_db = base.greeting_intro_voice_bed_db
        slot.greeting_intro_bed_variant = base.greeting_intro_bed_variant
        slot.greeting_intro_track_duck_db = base.greeting_intro_track_duck_db
        slot.greeting_intro_music_offset_sec = base.greeting_intro_music_offset_sec
        if audience == "unknown":
            slot.greeting_source = base.greeting_source
            slot.greeting_wav_path = base.greeting_wav_path
        if audience == "commercial":
            # Commercial : intro plus courte / optionnellement sans jingle.
            if slot.greeting_intro_mode is None:
                slot.greeting_intro_mode = "none"
            slot.greeting_intro_sec = 1.0
    elif audience == "commercial":
        slot.greeting_intro_mode = "none"
        slot.greeting_intro_sec = 1.0
    return slot


def ensure_audience_slots(audio: IncomingCallAudioConfig) -> IncomingCallAudioConfig:
    """
    Garantit les 3 slots known/unknown/commercial (migration legacy).

    Peuple depuis les champs plats si ``audiences`` est vide ou partiel.
    Synchronise aussi greeting_* plats depuis unknown pour compat.

    @param audio Bloc audio settings.
    @returns Meme instance mutee (audiences completes).
    """
    audiences = dict(audio.audiences or {})
    for key in GREETING_AUDIENCE_KEYS:
        raw = audiences.get(key)
        if raw is None:
            audiences[key] = default_audience_slot(key, audio)
            continue
        slot = raw if isinstance(raw, GreetingAudienceAudio) else GreetingAudienceAudio.model_validate(raw)
        if not (slot.greeting_tts_text or "").strip():
            slot.greeting_tts_text = DEFAULT_AUDIENCE_TEXTS[key]
        audiences[key] = slot
    audio.audiences = audiences

    unknown = audiences.get("unknown")
    if unknown is not None:
        if (unknown.greeting_tts_text or "").strip():
            audio.greeting_tts_text = unknown.greeting_tts_text
        if unknown.greeting_source:
            audio.greeting_source = unknown.greeting_source
        if unknown.greeting_wav_path is not None:
            audio.greeting_wav_path = unknown.greeting_wav_path

    commercial = audiences.get("commercial")
    if commercial is not None and (commercial.greeting_tts_text or "").strip():
        # Aligne le message bloque legacy sur l'accueil commercial.
        if not (audio.blocked_tts_text or "").strip():
            audio.blocked_tts_text = commercial.greeting_tts_text
    return audio


def resolve_audio_for_audience(
    settings: IncomingCallSettingsData,
    audience: GreetingAudienceKey,
) -> IncomingCallSettingsData:
    """
    Retourne une copie des settings avec audio effectif pour l'audience.

    Le slot audience ecrase greeting / voix / intro ; bip et blocked restent globaux.

    @param settings Settings incoming_call.
    @param audience Cle produit.
    @returns Copie profonde avec audio resolu (et audiences assurees).
    """
    merged = settings.model_copy(deep=True)
    ensure_audience_slots(merged.audio)
    key = normalize_audience(audience)
    slot = merged.audio.audiences.get(key) or default_audience_slot(key, merged.audio)
    data = merged.audio.model_dump()
    slot_dump = slot.model_dump(exclude_none=True)
    for field in _AUDIENCE_OVERRIDE_FIELDS:
        if field in slot_dump and slot_dump[field] is not None:
            data[field] = slot_dump[field]
    data["audiences"] = {k: v.model_dump() if hasattr(v, "model_dump") else v for k, v in merged.audio.audiences.items()}
    merged.audio = IncomingCallAudioConfig.model_validate(data)
    return merged


def greeting_text_for_audience(
    config: Config,
    settings: IncomingCallSettingsData,
    audience: GreetingAudienceKey,
) -> str:
    """
    Texte TTS d'accueil pour une audience.

    @param config Configuration (legacy voicemail_greeting).
    @param settings Settings (avec audiences).
    @param audience Cle produit.
    @returns Texte normalise une ligne.
    """
    resolved = resolve_audio_for_audience(settings, audience)
    custom = (resolved.audio.greeting_tts_text or "").strip()
    if custom:
        return " ".join(custom.split())
    legacy = (getattr(config, "voicemail_greeting", None) or "").strip()
    if legacy and normalize_audience(audience) == "unknown":
        return " ".join(legacy.split())
    return DEFAULT_AUDIENCE_TEXTS[normalize_audience(audience)]


def sync_flat_audio_from_audiences(audio: IncomingCallAudioConfig) -> None:
    """
    Recopie unknown/commercial vers les champs plats legacy apres edition UI.

    @param audio Bloc audio a muter.
    """
    ensure_audience_slots(audio)
    unknown = audio.audiences.get("unknown")
    if unknown is not None:
        if unknown.greeting_tts_text is not None:
            audio.greeting_tts_text = unknown.greeting_tts_text
        if unknown.greeting_source:
            audio.greeting_source = unknown.greeting_source
        if unknown.greeting_wav_path is not None:
            audio.greeting_wav_path = unknown.greeting_wav_path
        for field in (
            "tts_provider",
            "elevenlabs_voice_id",
            "edge_tts_voice",
            "edge_tts_rate",
            "edge_tts_pitch",
            "tts_voice_gain_db",
            "greeting_intro_mode",
            "greeting_intro_variant",
            "greeting_intro_wav_path",
            "greeting_intro_sec",
            "greeting_intro_crossfade_ms",
            "greeting_intro_voice_gain_db",
            "greeting_intro_voice_bed_db",
            "greeting_intro_bed_variant",
            "greeting_intro_track_duck_db",
            "greeting_intro_music_offset_sec",
        ):
            value = getattr(unknown, field, None)
            if value is not None:
                setattr(audio, field, value)
    commercial = audio.audiences.get("commercial")
    if commercial is not None and (commercial.greeting_tts_text or "").strip():
        audio.blocked_tts_text = commercial.greeting_tts_text
        audio.blocked_source = "tts"
