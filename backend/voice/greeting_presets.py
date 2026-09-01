"""
Textes et presets voix Edge TTS pour messages d'accueil repondeur.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GreetingTextPreset:
    """Texte d'accueil predefini pour preview ou config."""

    id: str
    label: str
    text: str


@dataclass(frozen=True)
class FemaleVoiceGreetingPreset:
    """Combinaison voix feminine + debit + hauteur + texte."""

    id: str
    label: str
    voice: str
    rate: str
    pitch: str
    text_id: str


GREETING_TEXT_PRESETS: tuple[GreetingTextPreset, ...] = (
    GreetingTextPreset(
        id="absent",
        label="Absence Monsieur Daniel",
        text=(
            "Bonjour, Monsieur Daniel est absent. "
            "Merci de laisser un message apres le bip."
        ),
    ),
    GreetingTextPreset(
        id="pro_classic",
        label="Professionnel classique",
        text=(
            "Bonjour. Vous etes bien chez Daniel Craft, de Loic Daniel. "
            "Merci de laisser votre message apres le bip."
        ),
    ),
    GreetingTextPreset(
        id="pro_warm",
        label="Chaleureux avec pauses",
        text=(
            "Bonjour. <break time=\"350ms\"/> "
            "Vous etes bien chez Daniel Craft, <break time=\"200ms\"/> "
            "de Loic Daniel. <break time=\"450ms\"/> "
            "Merci de laisser votre message apres le bip."
        ),
    ),
    GreetingTextPreset(
        id="formal",
        label="Formel cabinet",
        text=(
            "Bonjour. Daniel Craft, Loic Daniel, vous remercie de votre appel. "
            "Veuillez laisser votre nom, votre numero et votre message apres le signal sonore."
        ),
    ),
    GreetingTextPreset(
        id="short",
        label="Court et direct",
        text="Bonjour, Daniel Craft. Laissez votre message apres le bip. Merci.",
    ),
    GreetingTextPreset(
        id="friendly",
        label="Amical leger",
        text=(
            "Bonjour et merci de votre appel. <break time=\"300ms\"/> "
            "Ici Loic Daniel, Daniel Craft. <break time=\"400ms\"/> "
            "Je vous rappelle des que possible. A tout a l'heure sur le bip."
        ),
    ),
    GreetingTextPreset(
        id="evening",
        label="Hors horaires",
        text=(
            "Bonjour. Vous appelez Daniel Craft en dehors des horaires de bureau. "
            "Merci de laisser un message, nous vous recontacterons rapidement."
        ),
    ),
)


FEMALE_VOICE_GREETING_PRESETS: tuple[FemaleVoiceGreetingPreset, ...] = (
    FemaleVoiceGreetingPreset(
        id="denise_classic",
        label="Denise — neutre, classique",
        voice="fr-FR-DeniseNeural",
        rate="+0%",
        pitch="+0Hz",
        text_id="pro_classic",
    ),
    FemaleVoiceGreetingPreset(
        id="denise_warm",
        label="Denise — douce, pauses",
        voice="fr-FR-DeniseNeural",
        rate="-5%",
        pitch="+3Hz",
        text_id="pro_warm",
    ),
    FemaleVoiceGreetingPreset(
        id="eloise_soft",
        label="Eloise — tres douce",
        voice="fr-FR-EloiseNeural",
        rate="-8%",
        pitch="+1Hz",
        text_id="pro_warm",
    ),
    FemaleVoiceGreetingPreset(
        id="eloise_short",
        label="Eloise — message court",
        voice="fr-FR-EloiseNeural",
        rate="-3%",
        pitch="+0Hz",
        text_id="short",
    ),
    FemaleVoiceGreetingPreset(
        id="vivienne_friendly",
        label="Vivienne — amicale",
        voice="fr-FR-VivienneMultilingualNeural",
        rate="+0%",
        pitch="+7Hz",
        text_id="absent",
    ),
    FemaleVoiceGreetingPreset(
        id="charline_formal",
        label="Charline (BE) — formelle",
        voice="fr-BE-CharlineNeural",
        rate="-4%",
        pitch="-1Hz",
        text_id="formal",
    ),
    FemaleVoiceGreetingPreset(
        id="ariane_bright",
        label="Ariane (CH) — claire et leger haut",
        voice="fr-CH-ArianeNeural",
        rate="+2%",
        pitch="+4Hz",
        text_id="pro_classic",
    ),
    FemaleVoiceGreetingPreset(
        id="sylvie_calm",
        label="Sylvie (CA) — calme",
        voice="fr-CA-SylvieNeural",
        rate="-6%",
        pitch="+0Hz",
        text_id="evening",
    ),
    FemaleVoiceGreetingPreset(
        id="denise_low",
        label="Denise — grave, posée",
        voice="fr-FR-DeniseNeural",
        rate="-10%",
        pitch="-4Hz",
        text_id="formal",
    ),
    FemaleVoiceGreetingPreset(
        id="eloise_high",
        label="Eloise — aigue, dynamique",
        voice="fr-FR-EloiseNeural",
        rate="+3%",
        pitch="+6Hz",
        text_id="short",
    ),
)


def greeting_text_by_id(text_id: str) -> str:
    """
    Retourne le texte d'accueil pour un identifiant preset.

    @param text_id Identifiant GREETING_TEXT_PRESETS.
    @returns Texte ou classique par defaut.
    """
    for preset in GREETING_TEXT_PRESETS:
        if preset.id == text_id:
            return preset.text
    return GREETING_TEXT_PRESETS[0].text
