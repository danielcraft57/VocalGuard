"""
Prereglages audio pour la page Messages vocaux (voix, intro, outro).

Expose des combinaisons courantes de champs ``IncomingCallAudioConfig``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backend.voice.greeting_presets import greeting_text_by_id

AudioPresetCategory = Literal["voice", "intro", "outro"]


@dataclass(frozen=True)
class AudioPresetEntry:
    """Un prereglage audio (identifiant + patch de champs)."""

    id: str
    label: str
    description: str
    values: dict[str, Any]


VOICE_AUDIO_PRESETS: tuple[AudioPresetEntry, ...] = (
    AudioPresetEntry(
        id="denise_modem",
        label="Denise — modem (defaut)",
        description="Voix actuelle prod : douce, debit leger, volume attenue.",
        values={
            "edge_tts_voice": "fr-FR-DeniseNeural",
            "edge_tts_rate": "-4%",
            "edge_tts_pitch": "+3Hz",
            "tts_voice_gain_db": -6.0,
            "greeting_tts_text": greeting_text_by_id("pro_classic"),
        },
    ),
    AudioPresetEntry(
        id="denise_chaleureuse",
        label="Denise — chaleureuse",
        description="Plus lente et posée, ideal pour un accueil soigne.",
        values={
            "edge_tts_voice": "fr-FR-DeniseNeural",
            "edge_tts_rate": "-6%",
            "edge_tts_pitch": "+2Hz",
            "tts_voice_gain_db": -7.0,
            "greeting_tts_text": greeting_text_by_id("pro_classic"),
        },
    ),
    AudioPresetEntry(
        id="eloise_tendre",
        label="Eloise — tendre",
        description="Voix douce, debit calme, volume modere.",
        values={
            "edge_tts_voice": "fr-FR-EloiseNeural",
            "edge_tts_rate": "-8%",
            "edge_tts_pitch": "+1Hz",
            "tts_voice_gain_db": -7.0,
            "greeting_tts_text": greeting_text_by_id("pro_classic"),
        },
    ),
    AudioPresetEntry(
        id="vivienne_claire",
        label="Vivienne — claire",
        description="Ton leger et lumineux, debit neutre.",
        values={
            "edge_tts_voice": "fr-FR-VivienneMultilingualNeural",
            "edge_tts_rate": "+0%",
            "edge_tts_pitch": "+7Hz",
            "tts_voice_gain_db": -5.0,
            "greeting_tts_text": greeting_text_by_id("absent"),
        },
    ),
    AudioPresetEntry(
        id="henri_pro",
        label="Henri — professionnel",
        description="Voix masculine, grave et posee.",
        values={
            "edge_tts_voice": "fr-FR-HenriNeural",
            "edge_tts_rate": "-2%",
            "edge_tts_pitch": "-2Hz",
            "tts_voice_gain_db": -5.0,
            "greeting_tts_text": greeting_text_by_id("formal"),
        },
    ),
    AudioPresetEntry(
        id="charline_formelle",
        label="Charline — formelle (BE)",
        description="Accent belge, ton cabinet.",
        values={
            "edge_tts_voice": "fr-BE-CharlineNeural",
            "edge_tts_rate": "-4%",
            "edge_tts_pitch": "-1Hz",
            "tts_voice_gain_db": -6.0,
            "greeting_tts_text": greeting_text_by_id("formal"),
        },
    ),
    AudioPresetEntry(
        id="message_court",
        label="Message court",
        description="Texte bref, Denise neutre.",
        values={
            "edge_tts_voice": "fr-FR-DeniseNeural",
            "edge_tts_rate": "-3%",
            "edge_tts_pitch": "+0Hz",
            "tts_voice_gain_db": -6.0,
            "greeting_tts_text": greeting_text_by_id("short"),
        },
    ),
    AudioPresetEntry(
        id="hors_horaires",
        label="Hors horaires",
        description="Accueil bureau ferme, voix calme.",
        values={
            "edge_tts_voice": "fr-FR-DeniseNeural",
            "edge_tts_rate": "-5%",
            "edge_tts_pitch": "+1Hz",
            "tts_voice_gain_db": -6.0,
            "greeting_tts_text": greeting_text_by_id("evening"),
        },
    ),
)

INTRO_AUDIO_PRESETS: tuple[AudioPresetEntry, ...] = (
    AudioPresetEntry(
        id="tesla_court",
        label="Tesla — court (2,5 s)",
        description="Jingle actuel, intro breve avant la voix.",
        values={
            "greeting_intro_mode": "jingle",
            "greeting_intro_variant": "tesla",
            "greeting_intro_sec": 2.5,
            "greeting_intro_crossfade_ms": 380,
            "greeting_intro_voice_gain_db": 0.0,
            "greeting_intro_voice_bed_db": -18.0,
        },
    ),
    AudioPresetEntry(
        id="tesla_equilibre",
        label="Tesla — equilibre (4 s)",
        description="Jingle un peu plus long, fondu doux.",
        values={
            "greeting_intro_mode": "jingle",
            "greeting_intro_variant": "tesla",
            "greeting_intro_sec": 4.0,
            "greeting_intro_crossfade_ms": 450,
            "greeting_intro_voice_gain_db": 1.0,
            "greeting_intro_voice_bed_db": -18.0,
        },
    ),
    AudioPresetEntry(
        id="keywoo_doux",
        label="Keywoo — doux",
        description="Ambiance calme, intro medium.",
        values={
            "greeting_intro_mode": "jingle",
            "greeting_intro_variant": "keywoo",
            "greeting_intro_sec": 4.0,
            "greeting_intro_crossfade_ms": 420,
            "greeting_intro_voice_gain_db": 0.0,
            "greeting_intro_voice_bed_db": -18.0,
        },
    ),
    AudioPresetEntry(
        id="electronika_dynamique",
        label="Electronika — dynamique",
        description="Jingle rythme, intro courte.",
        values={
            "greeting_intro_mode": "jingle",
            "greeting_intro_variant": "electronika",
            "greeting_intro_sec": 3.0,
            "greeting_intro_crossfade_ms": 350,
            "greeting_intro_voice_gain_db": 2.0,
            "greeting_intro_voice_bed_db": -18.0,
        },
    ),
    AudioPresetEntry(
        id="high_energie",
        label="High — energie",
        description="Intro punchy, fondu rapide.",
        values={
            "greeting_intro_mode": "jingle",
            "greeting_intro_variant": "high",
            "greeting_intro_sec": 3.5,
            "greeting_intro_crossfade_ms": 320,
            "greeting_intro_voice_gain_db": 2.0,
            "greeting_intro_voice_bed_db": -18.0,
        },
    ),
    AudioPresetEntry(
        id="piste_iceland",
        label="Piste Iceland — solo puis voix",
        description="Musique de fond puis annonce par-dessus.",
        values={
            "greeting_intro_mode": "track",
            "greeting_intro_wav_path": "resources/voice/music/whispering_iceland.mp3",
            "greeting_intro_sec": 3.0,
            "greeting_intro_crossfade_ms": 400,
            "greeting_intro_track_duck_db": 0.0,
            "greeting_intro_music_offset_sec": 0.0,
        },
    ),
    AudioPresetEntry(
        id="sans_intro",
        label="Sans intro",
        description="Voix seule, pas de jingle.",
        values={
            "greeting_intro_mode": "none",
        },
    ),
)

OUTRO_AUDIO_PRESETS: tuple[AudioPresetEntry, ...] = (
    AudioPresetEntry(
        id="classique_modem",
        label="Classique modem",
        description="Bip WAV standard + message bloque pre-enregistre.",
        values={
            "record_beep": "wav",
            "record_beep_wav_path": "resources/voice/system/beep.wav",
            "blocked_source": "wav",
            "blocked_wav_path": "resources/voice/system/blocked_short.wav",
            "blocked_tts_text": None,
        },
    ),
    AudioPresetEntry(
        id="bip_dtmf",
        label="Bip tonalite DTMF",
        description="Bip synthetique modem, message bloque WAV.",
        values={
            "record_beep": "dtmf",
            "record_beep_wav_path": "resources/voice/system/beep.wav",
            "blocked_source": "wav",
            "blocked_wav_path": "resources/voice/system/blocked_short.wav",
            "blocked_tts_text": None,
        },
    ),
    AudioPresetEntry(
        id="sans_bip",
        label="Sans bip",
        description="Enregistrement direct apres l'accueil, sans signal.",
        values={
            "record_beep": "none",
            "record_beep_wav_path": "resources/voice/system/beep.wav",
            "blocked_source": "wav",
            "blocked_wav_path": "resources/voice/system/blocked_short.wav",
            "blocked_tts_text": None,
        },
    ),
    AudioPresetEntry(
        id="bloque_vocal",
        label="Bloque vocal (TTS)",
        description="Bip WAV + refus d'appel synthetise.",
        values={
            "record_beep": "wav",
            "record_beep_wav_path": "resources/voice/system/beep.wav",
            "blocked_source": "tts",
            "blocked_wav_path": "resources/voice/system/blocked_short.wav",
            "blocked_tts_text": "Desole, cet appel ne peut pas etre accepte. Au revoir.",
        },
    ),
    AudioPresetEntry(
        id="discret_complet",
        label="Discret (sans bip, bloque TTS)",
        description="Pas de bip, refus court en voix synthetique.",
        values={
            "record_beep": "none",
            "record_beep_wav_path": "resources/voice/system/beep.wav",
            "blocked_source": "tts",
            "blocked_wav_path": "resources/voice/system/blocked_short.wav",
            "blocked_tts_text": "Appel refuse. Merci de rappeler plus tard.",
        },
    ),
)

_CATEGORY_MAP: dict[AudioPresetCategory, tuple[AudioPresetEntry, ...]] = {
    "voice": VOICE_AUDIO_PRESETS,
    "intro": INTRO_AUDIO_PRESETS,
    "outro": OUTRO_AUDIO_PRESETS,
}


def _serialize_preset(entry: AudioPresetEntry) -> dict[str, Any]:
    """
    Convertit un preset en dict JSON-safe.

    @param entry Entree catalogue.
    @returns Dict serialisable API.
    """
    return {
        "id": entry.id,
        "label": entry.label,
        "description": entry.description,
        "values": entry.values,
    }


def list_audio_presets(category: AudioPresetCategory | None = None) -> dict[str, list[dict[str, Any]]]:
    """
    Liste les prereglages audio par categorie.

    @param category Filtre optionnel (voice, intro, outro).
    @returns Dictionnaire categorie -> presets.
    """
    if category:
        rows = _CATEGORY_MAP.get(category, ())
        return {category: [_serialize_preset(row) for row in rows]}
    return {
        key: [_serialize_preset(row) for row in rows]
        for key, rows in _CATEGORY_MAP.items()
    }


def get_audio_preset(category: AudioPresetCategory, preset_id: str) -> dict[str, Any] | None:
    """
    Retourne un preset par categorie et identifiant.

    @param category voice | intro | outro.
    @param preset_id Identifiant stable.
    @returns Preset serialise ou None.
    """
    needle = (preset_id or "").strip().lower()
    for entry in _CATEGORY_MAP.get(category, ()):
        if entry.id.lower() == needle:
            return _serialize_preset(entry)
    return None
