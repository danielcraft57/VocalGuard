"""
Chemins standardises pour les assets audio VocalGuard (modem / repondeur).

Structure :
  resources/voice/system/   — bip, message bloque (fichiers fixes)
  resources/voice/intros/   — jingles d'accueil (variantes + default.wav actif)
  resources/voice/lab/      — previews locales generees (jingles, voix, sequences)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

VOICE_ROOT = Path("resources") / "voice"
SYSTEM_DIR = VOICE_ROOT / "system"
INTROS_DIR = VOICE_ROOT / "intros"
MUSIC_DIR = VOICE_ROOT / "music"
LAB_DIR = VOICE_ROOT / "lab"
LAB_JINGLES_DIR = LAB_DIR / "jingles"
LAB_GREETINGS_DIR = LAB_DIR / "greetings"
LAB_SEQUENCES_DIR = LAB_DIR / "sequences"
LAB_BEDS_DIR = LAB_DIR / "beds"

# Chemins canoniques (relatifs a la racine projet).
BEEP_WAV = SYSTEM_DIR / "beep.wav"
BLOCKED_WAV = SYSTEM_DIR / "blocked_short.wav"
INTRO_DEFAULT_WAV = INTROS_DIR / "default.wav"
WHISPERING_ICELAND_MP3 = MUSIC_DIR / "whispering_iceland.mp3"

# Anciens chemins (compat config existante).
LEGACY_BEEP_WAV = VOICE_ROOT / "beep.wav"
LEGACY_BLOCKED_WAV = VOICE_ROOT / "blocked_short.wav"
LEGACY_INTRO_WAV = VOICE_ROOT / "greeting_intro.wav"


def voice_root(config_base: Optional[Path] = None) -> Path:
    """
    Racine resources/voice absolue.

    @param config_base Racine projet (Config.base_path).
    @returns Chemin absolu.
    """
    base = config_base if config_base else Path.cwd()
    return base / VOICE_ROOT


def ensure_voice_tree(config_base: Optional[Path] = None) -> Path:
    """
    Cree l'arborescence voice/ si absente.

    @param config_base Racine projet.
    @returns Racine voice absolue.
    """
    base = config_base if config_base else Path.cwd()
    root = base / VOICE_ROOT
    for rel in (SYSTEM_DIR, INTROS_DIR, LAB_JINGLES_DIR, LAB_GREETINGS_DIR, LAB_SEQUENCES_DIR, LAB_BEDS_DIR):
        (base / rel).mkdir(parents=True, exist_ok=True)
    return root


def intro_variant_path(variant: str, config_base: Optional[Path] = None) -> Path:
    """
    Chemin WAV pour une variante de jingle.

    @param variant Identifiant (pad_warm, sfr_a, ...).
    @param config_base Racine projet.
    @returns Chemin intros/{variant}.wav.
    """
    base = config_base if config_base else Path.cwd()
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in variant.strip()) or "default"
    return base / INTROS_DIR / f"{safe}.wav"


def resolve_voice_asset(
    config_base: Optional[Path],
    relative: Optional[str],
    *,
    legacy_candidates: tuple[Path, ...] = (),
) -> Optional[Path]:
    """
    Resout un asset audio : chemin configure, puis candidats legacy.

    @param config_base Racine projet.
    @param relative Chemin relatif configure.
    @param legacy_candidates Anciens chemins a tenter si le principal manque.
    @returns Path absolu si fichier existe.
    """
    base = config_base if config_base else Path.cwd()
    if relative and str(relative).strip():
        raw = Path(str(relative).strip())
        candidate = raw if raw.is_absolute() else base / raw
        try:
            resolved = candidate.resolve()
            if resolved.is_file():
                return resolved
        except OSError:
            pass
    for leg in legacy_candidates:
        candidate = base / leg
        try:
            resolved = candidate.resolve()
            if resolved.is_file():
                return resolved
        except OSError:
            continue
    return None


def resolve_intro_wav(config_base: Optional[Path], configured: Optional[str] = None) -> Optional[Path]:
    """
    Resout le WAV d'intro (nouveau layout + legacy greeting_intro.wav).

    @param config_base Racine projet.
    @param configured Chemin override config.
    @returns Path ou None.
    """
    return resolve_voice_asset(
        config_base,
        configured or str(INTRO_DEFAULT_WAV),
        legacy_candidates=(LEGACY_INTRO_WAV,),
    )


def resolve_beep_wav(config_base: Optional[Path], configured: Optional[str] = None) -> Optional[Path]:
    """
    Resout le bip d'enregistrement.

    @param config_base Racine projet.
    @param configured Chemin override config.
    @returns Path ou None.
    """
    return resolve_voice_asset(
        config_base,
        configured or str(BEEP_WAV),
        legacy_candidates=(LEGACY_BEEP_WAV,),
    )


def resolve_blocked_wav(config_base: Optional[Path], configured: Optional[str] = None) -> Optional[Path]:
    """
    Resout le WAV message bloque.

    @param config_base Racine projet.
    @param configured Chemin override config.
    @returns Path ou None.
    """
    return resolve_voice_asset(
        config_base,
        configured or str(BLOCKED_WAV),
        legacy_candidates=(LEGACY_BLOCKED_WAV,),
    )
