"""
Construction du mix accueil (TTS source + intro + bip) — utilisable localement ou sur node15.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from loguru import logger

from backend.voice.audio_utils import (
    combine_intro_voice_crossfade,
    combine_music_track_voice_overlay,
    default_bed_variant_for_jingle,
    export_listen_preview_wav,
    export_wav_8k_8bit,
    load_audio_segment_modem,
    trim_leading_trailing_silence,
    tts_source_to_modem_wav,
)
from backend.voice.modem_profile import (
    CONEXANT_VOICE_PROFILE,
    ModemVoiceProfile,
    USR_FALLBACK_PROFILE,
    USR_VOICE_PROFILE,
)
from backend.voice.musicscreen_jingles import is_musicscreen_jingle


@dataclass(frozen=True)
class GreetingMixParams:
    """Parametres de mix accueil (hors fichiers)."""

    intro_mode: str = "none"
    intro_variant: str = "tesla"
    intro_sec: float = 2.2
    crossfade_ms: int = 380
    voice_bed_db: float = -18.0
    voice_mix_gain_db: float = 0.0
    track_duck_db: float = 0.0
    music_offset_sec: float = 0.0
    bed_variant: Optional[str] = None
    sample_rate: int = 11025
    sample_width: int = 2
    tts_voice_gain_db: float = -6.0
    append_beep: bool = True
    beep_gap_ms: int = 500
    output: Literal["modem", "listen", "voice"] = "modem"


def profile_from_hw(sample_rate: int, sample_width: int) -> ModemVoiceProfile:
    """
    Profil modem depuis rate / sample width.

    @param sample_rate Frequence cible.
    @param sample_width Octets par sample.
    @returns Profil connu ou ad-hoc.
    """
    rate = int(sample_rate)
    width = int(sample_width)
    if rate == USR_VOICE_PROFILE.sample_rate and width == USR_VOICE_PROFILE.sample_width:
        return USR_VOICE_PROFILE
    if rate == USR_FALLBACK_PROFILE.sample_rate and width == USR_FALLBACK_PROFILE.sample_width:
        return USR_FALLBACK_PROFILE
    if rate == CONEXANT_VOICE_PROFILE.sample_rate and width == CONEXANT_VOICE_PROFILE.sample_width:
        return CONEXANT_VOICE_PROFILE
    return ModemVoiceProfile(
        name="custom",
        sample_rate=rate,
        sample_width=width,
        vsm_command=f"AT+VSM=0,{rate}",
        baudrate=115200,
        ffmpeg_codec="pcm_s16le" if width >= 2 else "pcm_u8",
    )


def _resolve_bed_db(voice_bed_db: float) -> Optional[float]:
    """
    Convertit le bed UI en gain sous voix (None = desactive).

    @param voice_bed_db Valeur settings (souvent negative).
    @returns Gain dB ou None.
    """
    bed_db = float(voice_bed_db)
    if bed_db > -1.0:
        return None
    return bed_db


def append_beep_file_to_modem_wav(
    wav_path: Path,
    beep_path: Path,
    *,
    profile: ModemVoiceProfile,
    gap_ms: int = 500,
) -> None:
    """
    Colle un bip a la fin d'un WAV modem.

    @param wav_path Accueil a modifier sur place.
    @param beep_path Fichier bip.
    @param profile Profil modem.
    @param gap_ms Silence avant le bip.
    """
    if not wav_path.is_file() or not beep_path.is_file():
        return
    main = load_audio_segment_modem(wav_path)
    main = trim_leading_trailing_silence(main, padding_ms=0)
    beep_seg = load_audio_segment_modem(beep_path)
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


def build_greeting_mix_from_tts_source(
    tts_source: Path,
    out_path: Path,
    *,
    params: GreetingMixParams,
    intro_path: Optional[Path] = None,
    beep_path: Optional[Path] = None,
) -> Path:
    """
    Convertit la source TTS, mixe intro/voix, optionnellement bip, exporte modem ou listen.

    @param tts_source Fichier edge-tts (mp3/wav).
    @param out_path Destination finale.
    @param params Parametres de mix.
    @param intro_path Intro musicale optionnelle.
    @param beep_path Bip optionnel.
    @returns Chemin ``out_path``.
    @raises RuntimeError Si conversion / mix impossible.
    """
    profile = profile_from_hw(params.sample_rate, params.sample_width)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = out_path.parent / f".mix_{out_path.stem}"
    work_dir.mkdir(parents=True, exist_ok=True)
    voice_modem = work_dir / "voice_modem.wav"
    modem_out = work_dir / "modem.wav"

    try:
        tts_source_to_modem_wav(
            Path(tts_source),
            voice_modem,
            profile=profile,
            voice_gain_db=float(params.tts_voice_gain_db),
        )
        if not voice_modem.is_file() or voice_modem.stat().st_size < 100:
            raise RuntimeError("Conversion TTS modem echouee")

        if params.output == "voice":
            export_listen_preview_wav(voice_modem, out_path, target_peak=None)
            return out_path

        intro_mode = (params.intro_mode or "none").strip().lower()
        intro = Path(intro_path) if intro_path and Path(intro_path).is_file() else None

        if intro_mode == "track" and intro is not None:
            intro_ms = int(float(params.intro_sec or 0.0) * 1000)
            crossfade_ms = int(params.crossfade_ms or 450)
            music_offset_ms = int(float(params.music_offset_sec or 0.0) * 1000)
            track_duck_db = float(params.track_duck_db or 0.0)
            combine_music_track_voice_overlay(
                intro,
                voice_modem,
                modem_out,
                music_solo_ms=intro_ms,
                music_offset_ms=music_offset_ms,
                voice_fade_ms=crossfade_ms,
                music_duck_db=track_duck_db if track_duck_db > 0.5 else None,
                voice_mix_gain_db=float(params.voice_mix_gain_db or 0.0),
            )
        elif intro_mode in ("jingle", "wav") and intro is not None:
            intro_ms = int(float(params.intro_sec or 2.2) * 1000)
            crossfade_ms = int(params.crossfade_ms or 280)
            intro_variant = str(params.intro_variant or "tesla")
            bed_db = _resolve_bed_db(float(params.voice_bed_db))
            bed_variant = params.bed_variant
            if bed_variant is None and not is_musicscreen_jingle(intro_variant):
                bed_variant = default_bed_variant_for_jingle(intro_variant)
            combine_intro_voice_crossfade(
                intro,
                voice_modem,
                modem_out,
                crossfade_ms=crossfade_ms,
                intro_max_ms=intro_ms,
                intro_variant=intro_variant,
                normalize=True,
                voice_bed_gain_db=bed_db,
                voice_mix_gain_db=float(params.voice_mix_gain_db or 0.0),
                voice_bed_variant=str(bed_variant) if bed_variant else None,
                profile=profile,
            )
        else:
            shutil.copy2(voice_modem, modem_out)

        if params.append_beep and beep_path and Path(beep_path).is_file():
            append_beep_file_to_modem_wav(
                modem_out,
                Path(beep_path),
                profile=profile,
                gap_ms=int(params.beep_gap_ms),
            )

        if params.output == "listen":
            export_listen_preview_wav(modem_out, out_path, target_peak=None)
        else:
            shutil.copy2(modem_out, out_path)

        if not out_path.is_file() or out_path.stat().st_size < 200:
            raise RuntimeError("Mix accueil vide")
        logger.debug(
            "Mix accueil OK mode={} out={} ({} octets)",
            intro_mode,
            out_path.name,
            out_path.stat().st_size,
        )
        return out_path
    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except OSError:
            pass
