"""
Utilitaires audio pour IVR / modem (Conexant).
Export WAV 8 kHz, mono, 8-bit pour compatibilité modem voix (callattendant, VocalGuard).
Lecture et conversion pour STT (16 kHz 16-bit).
"""

import math
import re
import subprocess
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from pydub import AudioSegment

MODEM_SAMPLE_RATE = 8000
# Cible pic voix avant mix (dBFS approximatif via pydub max).
MODEM_VOICE_PEAK_TARGET = 28000
# Pic max apres mix musique+voix (evite saturation u8=127 sur le modem).
MODEM_MIX_PEAK_TARGET = 18500
MODEM_U8_PEAK_DEVIATION = 120
# Filtre telephone + resampling haute qualite (ffmpeg soxr).
_FFMPEG_TELEPHONY_FILTERS = (
    "highpass=f=120,lowpass=f=3600,"
    "aresample=resampler=soxr:osr=8000:precision=28:cheby=1"
)


def _ffmpeg_available() -> bool:
    """
    Verifie si ffmpeg est disponible sur le systeme.

    @returns True si la commande ffmpeg repond.
    """
    try:
        proc = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=8,
            check=False,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def ffmpeg_convert_to_modem_wav(
    input_path: Path,
    output_path: Path,
    *,
    normalize: bool = True,
    extra_af: str = "",
) -> Path:
    """
    Convertit un fichier audio en WAV modem 8 kHz mono 8-bit via ffmpeg (soxr + EQ telephone).

    @param input_path Source MP3/WAV/etc.
    @param output_path Destination WAV u8.
    @param normalize Applique une normalisation douce dynaudnorm.
    @param extra_af Filtres audio supplementaires (chaine ffmpeg).
    @returns Chemin de sortie.
    @raises RuntimeError Si ffmpeg echoue.
    """
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg indisponible pour conversion modem HQ")

    filters = _FFMPEG_TELEPHONY_FILTERS
    if extra_af:
        filters = f"{filters},{extra_af}"
    if normalize:
        filters += ",dynaudnorm=f=90:g=8:p=0.92"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-ar",
        str(MODEM_SAMPLE_RATE),
        "-ac",
        "1",
        "-af",
        filters,
        "-c:a",
        "pcm_u8",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"ffmpeg conversion modem echouee: {err}")
    return output_path


def normalize_segment_peak(segment: "AudioSegment", *, target_peak: int = MODEM_VOICE_PEAK_TARGET) -> "AudioSegment":
    """
    Normalise un segment sur son pic d'amplitude (preserve la dynamique relative).

    @param segment Audio pydub.
    @param target_peak Pic cible 16-bit (ex. 20000).
    @returns Segment normalise.
    """
    peak = segment.max or 0
    if peak <= 0:
        return segment
    gain_db = 20.0 * math.log10(float(target_peak) / float(peak))
    if abs(gain_db) < 0.05:
        return segment
    return segment.apply_gain(gain_db)


def limit_segment_peak(segment: "AudioSegment", *, target_peak: int = MODEM_MIX_PEAK_TARGET) -> "AudioSegment":
    """
    Baisse le niveau si le pic depasse la cible (anti-clipping sur ligne modem 8-bit).

    @param segment Audio pydub.
    @param target_peak Pic maximum 16-bit autorise avant export u8.
    @returns Segment limite si necessaire.
    """
    peak = segment.max or 0
    if peak <= target_peak or peak <= 0:
        return segment
    gain_db = 20.0 * math.log10(float(target_peak) / float(peak))
    return segment.apply_gain(gain_db)


def tts_source_to_modem_wav(source_path: Path, out_path: Path) -> Path:
    """
    Pipeline TTS -> WAV modem : trim leger puis conversion ffmpeg HQ.

    @param source_path MP3/WAV edge-tts.
    @param out_path WAV 8 kHz 8-bit.
    @returns Chemin genere.
    """
    from pydub import AudioSegment

    segment = AudioSegment.from_file(str(source_path))
    segment = trim_leading_trailing_silence(
        segment,
        silence_threshold=-48.0,
        padding_ms=40,
    )
    segment = normalize_segment_peak(segment)

    if _ffmpeg_available():
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            segment.export(str(tmp_path), format="wav")
            return ffmpeg_convert_to_modem_wav(tmp_path, out_path, normalize=False)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    export_wav_8k_8bit(segment, out_path, normalize=True)
    return out_path


def jingle_last_note_hz(variant: str) -> float:
    """
    Frequence de la derniere note d'un jingle (pour caler le pitch TTS).

    @param variant Identifiant jingle (sting_marimba, sfr_a, ...).
    @returns Frequence Hz ou 0 si inconnu.
    """
    if variant in _STINGER_SCORES:
        return float(_STINGER_SCORES[variant]["notes"][-1][0])
    if variant in _TELECOM_INTRO_SCORES:
        return float(_TELECOM_INTRO_SCORES[variant][-1][0])
    return 0.0


def recommended_edge_tts_pitch_for_jingle(variant: str) -> str:
    """
    Offset pitch Edge TTS suggere pour prolonger la tonalite de la derniere note du jingle.

    @param variant Identifiant jingle.
    @returns Chaine pitch edge-tts (ex. "+7Hz").
    """
    last_hz = jingle_last_note_hz(variant)
    if last_hz <= 0:
        return "+2Hz"
    reference_hz = 523.25
    semitones = 12.0 * math.log2(last_hz / reference_hz)
    offset_hz = int(round(max(0, min(12, semitones * 0.55))))
    if offset_hz <= 0:
        return "+0Hz"
    return f"+{offset_hz}Hz"


def estimated_jingle_melody_end_ms(variant: str, duration_ms: int) -> int:
    """
    Estime la fin du motif melodique (evite le silence apres le jingle).

    @param variant Identifiant jingle.
    @param duration_ms Duree max de generation du WAV intro.
    @returns Duree effective en ms jusqu'a la fin de la melodie (+ courte queue).
    """
    notes: list[tuple[float, float]] | None = None
    overlap = 0.80
    if variant in _STINGER_SCORES:
        spec = _STINGER_SCORES[variant]
        notes = spec["notes"]
        overlap = float(spec.get("overlap", 0.78))
    elif variant in _TELECOM_INTRO_SCORES:
        notes = _TELECOM_INTRO_SCORES[variant]
        overlap = 0.82
    if not notes:
        return duration_ms

    total_note_sec = sum(d for _, d in notes)
    scale = min(1.0, (duration_ms / 1000.0) / max(total_note_sec, 0.1))
    pos_ms = 0
    for _, note_sec in notes:
        note_ms = max(1, int(note_sec * scale * 1000))
        pos_ms += max(1, int(note_ms * overlap))
    return min(duration_ms, pos_ms + 90)


def trim_intro_for_voice_handoff(intro: "AudioSegment", *, tail_padding_ms: int = 50) -> "AudioSegment":
    """
    Retire le silence de fin du jingle pour enchaîner vite vers la voix.

    @param intro Segment intro charge.
    @param tail_padding_ms Marge apres la derniere note audible.
    @returns Intro rognee.
    """
    intro = trim_leading_trailing_silence(intro, silence_threshold=-44.0, padding_ms=10)
    intro = trim_leading_trailing_silence(intro, silence_threshold=-40.0, padding_ms=tail_padding_ms)
    return intro


def write_beep_wav_8k(out_path: Path, *, freq_hz: int = 1000, duration_ms: int = 500) -> None:
    """
    Genere un bip unique court (8 kHz, mono, 8-bit), style repondeur classique.

    @param out_path Fichier WAV de sortie.
    @param freq_hz Frequence du bip en hertz.
    @param duration_ms Duree du bip en millisecondes.
    """
    rate = 8000
    sample_count = max(1, int(rate * duration_ms / 1000))
    samples = bytearray(sample_count)
    amplitude = 126
    fade = max(1, int(rate * 0.01))  # 10 ms fade in/out anti-clic
    for i in range(sample_count):
        t = i / rate
        env = 1.0
        if i < fade:
            env = i / fade
        elif i > sample_count - fade:
            env = (sample_count - i) / fade
        wave_val = math.sin(2.0 * math.pi * freq_hz * t) * env
        value = 128 + int(amplitude * wave_val)
        samples[i] = max(0, min(255, value))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(rate)
        wf.writeframes(bytes(samples))


def normalize_pcm_u8_buffer(
    data: bytes,
    *,
    target_deviation: int = MODEM_U8_PEAK_DEVIATION,
) -> bytes:
    """
    Normalise un buffer PCM 8-bit non signe (128 = silence) pour le VTX modem.

    @param data Octets PCM u8 mono.
    @param target_deviation Amplitude cible autour de 128 (ex. 120).
    @returns Buffer re-gaine si trop faible.
    """
    if not data:
        return data
    peak = max((abs(b - 128) for b in data), default=0)
    if peak <= 0:
        return data
    if peak >= int(target_deviation * 0.92):
        return data
    gain = float(target_deviation) / float(peak)
    out = bytearray(len(data))
    for index, sample in enumerate(data):
        centered = (sample - 128) * gain
        out[index] = max(0, min(255, int(round(128 + centered))))
    return bytes(out)


def _adsr_envelope(
    sample_index: int,
    note_samples: int,
    *,
    attack_ratio: float = 0.08,
    release_ratio: float = 0.22,
) -> float:
    """
    Enveloppe ADSR simplifiee pour une note.

    @param sample_index Index dans la note.
    @param note_samples Duree totale de la note en echantillons.
    @param attack_ratio Part attaque (0-1).
    @param release_ratio Part release (0-1).
    @returns Gain 0..1.
    """
    if note_samples <= 0:
        return 0.0
    attack = max(1, int(note_samples * attack_ratio))
    release = max(1, int(note_samples * release_ratio))
    sustain_start = attack
    sustain_end = max(sustain_start, note_samples - release)
    if sample_index < attack:
        return sample_index / float(attack)
    if sample_index < sustain_end:
        return 1.0
    if sample_index < note_samples:
        return max(0.0, (note_samples - sample_index) / float(release))
    return 0.0


def _telecom_bell_wave(t: float, freq_hz: float, env: float) -> float:
    """
    Timbre cloche / piano electrique type messagerie operateur (composition originale).

    @param t Temps en secondes dans la note.
    @param freq_hz Frequence fondamentale.
    @param env Enveloppe amplitude.
    @returns Echantillon -1..1.
    """
    phase = 2.0 * math.pi * freq_hz * t
    wave_val = math.sin(phase) * 0.62
    wave_val += math.sin(phase * 2.01) * 0.24
    wave_val += math.sin(phase * 3.05) * 0.10
    wave_val += math.sin(phase * 4.2) * 0.04
    return wave_val * env


# Motifs originaux inspires du style messagerie mobile francaise (arpège clair, majeur).
_TELECOM_INTRO_SCORES: dict[str, list[tuple[float, float]]] = {
    "sfr_a": [
        (392.00, 0.36),
        (493.88, 0.36),
        (587.33, 0.38),
        (783.99, 0.52),
        (987.77, 0.55),
    ],
    # Plus court, staccato operateur
    "sfr_b": [
        (523.25, 0.28),
        (659.25, 0.28),
        (783.99, 0.30),
        (1046.50, 0.45),
    ],
    # Variante douce avec redescente (fin type bande-annonce)
    "sfr_c": [
        (440.00, 0.32),
        (554.37, 0.32),
        (659.25, 0.34),
        (880.00, 0.40),
        (659.25, 0.30),
        (554.37, 0.42),
    ],
}


# Stingers type "corporate intro" (7-15 s) : melodie claire, sans pad etouffant.
# Inspires des styles happy corporate / startup / business hold music (compositions originales).
_STINGER_SCORES: dict[str, dict] = {
    "sting_corporate": {
        "timbre": "piano",
        "overlap": 0.78,
        "notes": [
            (523.25, 0.20),
            (659.25, 0.20),
            (783.99, 0.22),
            (1046.50, 0.28),
            (1318.51, 0.38),
        ],
    },
    "sting_startup": {
        "timbre": "synth",
        "overlap": 0.58,
        "notes": [
            (392.00, 0.16),
            (493.88, 0.16),
            (587.33, 0.18),
            (783.99, 0.26),
            (987.77, 0.34),
        ],
    },
    "sting_marimba": {
        "timbre": "marimba",
        "overlap": 0.74,
        "key": "La majeur",
        "note_names": ["La4", "Do#5", "Mi5", "La5", "Mi5"],
        "notes": [
            (440.00, 0.26),
            (554.37, 0.24),
            (659.25, 0.26),
            (880.00, 0.30),
            (659.25, 0.38),
        ],
    },
    "sting_acoustic": {
        "timbre": "acoustic",
        "overlap": 0.80,
        "notes": [
            (349.23, 0.30),
            (440.00, 0.28),
            (523.25, 0.30),
            (659.25, 0.38),
            (783.99, 0.42),
        ],
    },
    "sting_mini": {
        "timbre": "piano",
        "overlap": 0.72,
        "notes": [
            (587.33, 0.16),
            (739.99, 0.16),
            (880.00, 0.24),
            (1174.66, 0.30),
        ],
    },
    "sting_bell": {
        "timbre": "bell",
        "overlap": 0.82,
        "notes": [
            (392.00, 0.36),
            (493.88, 0.36),
            (587.33, 0.38),
            (783.99, 0.52),
            (987.77, 0.55),
        ],
    },
}


# Fonds musicaux composes sous la voix d'accueil (partitions separees du jingle).
_VOICE_BED_SCORES: dict[str, dict] = {
    "bed_marimba_warm": {
        "label": "Marimba doux — La majeur",
        "root_hz": 220.0,
        "chord": (1.0, 1.26, 1.5, 2.0),
        "arp": [(1.0, 0.55), (1.26, 0.50), (1.5, 0.50), (1.26, 0.48)],
        "note_names": ["La3", "Do#4", "Mi4", "Do#4"],
        "timbre": "marimba",
        "pad_gain": 0.16,
        "arp_gain": 0.38,
        "loop_overlap": 0.90,
    },
    "bed_corporate_pad": {
        "label": "Pad corporate — Do majeur",
        "root_hz": 261.63,
        "chord": (1.0, 1.25, 1.5, 2.0),
        "arp": [(1.0, 0.65), (1.25, 0.55), (1.5, 0.60)],
        "note_names": ["Do4", "Mi4", "Sol4"],
        "timbre": "piano",
        "pad_gain": 0.20,
        "arp_gain": 0.30,
        "loop_overlap": 0.92,
    },
    "bed_calm_wave": {
        "label": "Vague calme — Sol majeur",
        "root_hz": 196.0,
        "chord": (1.0, 1.22, 1.5, 1.87),
        "arp": [(1.22, 0.58), (1.0, 0.52), (1.5, 0.55), (1.22, 0.50)],
        "note_names": ["Si3", "Sol3", "Re4", "Si3"],
        "timbre": "acoustic",
        "pad_gain": 0.15,
        "arp_gain": 0.34,
        "loop_overlap": 0.88,
    },
    "bed_amber_resolve": {
        "label": "Ambre — Si majeur, resolution douce",
        "root_hz": 246.94,
        "chord": (1.0, 1.26, 1.5, 1.78),
        "arp": [(1.0, 0.52), (1.26, 0.48), (1.5, 0.50), (1.26, 0.46)],
        "note_names": ["Si3", "Re#4", "Fa#4", "Re#4"],
        "timbre": "marimba",
        "pad_gain": 0.17,
        "arp_gain": 0.36,
        "loop_overlap": 0.90,
    },
}

# Jingle d'intro -> fond sous la voix (si bed non choisi manuellement).
_JINGLE_DEFAULT_BED: dict[str, str] = {
    "sting_marimba": "bed_marimba_warm",
    "sting_corporate": "bed_corporate_pad",
    "sting_startup": "bed_corporate_pad",
    "sting_acoustic": "bed_calm_wave",
    "sting_mini": "bed_corporate_pad",
    "sting_bell": "bed_amber_resolve",
    "sfr_a": "bed_corporate_pad",
    "sfr_b": "bed_amber_resolve",
    "sfr_c": "bed_calm_wave",
}


# Jingles avec fond musical leger (pad + melodie) — legacy, peu recommande.
_PAD_JINGLE_SCORES: dict[str, dict] = {
    "pad_warm": {
        "root_hz": 261.63,
        "chord": (1.0, 1.25, 1.5, 2.0),
        "pad_gain": 0.06,
        "melody_gain": 0.72,
        "notes": [(523.25, 0.32), (659.25, 0.30), (783.99, 0.36), (1046.50, 0.42)],
        "tail_fade_ratio": 0.24,
    },
    "pad_soft": {
        "root_hz": 220.0,
        "chord": (1.0, 1.2, 1.5, 1.8),
        "pad_gain": 0.05,
        "melody_gain": 0.66,
        "notes": [(440.0, 0.34), (554.37, 0.32), (659.25, 0.38), (880.0, 0.40)],
        "tail_fade_ratio": 0.28,
    },
    "pad_bright": {
        "root_hz": 392.0,
        "chord": (1.0, 1.26, 1.5, 2.0),
        "pad_gain": 0.055,
        "melody_gain": 0.74,
        "notes": [(587.33, 0.26), (739.99, 0.26), (880.0, 0.30), (1174.66, 0.36)],
        "tail_fade_ratio": 0.22,
    },
    "pad_calm": {
        "root_hz": 293.66,
        "chord": (1.0, 1.22, 1.5, 1.89),
        "pad_gain": 0.045,
        "melody_gain": 0.64,
        "notes": [(587.33, 0.38), (659.25, 0.34), (783.99, 0.40), (659.25, 0.36)],
        "tail_fade_ratio": 0.30,
    },
    "pad_mini": {
        "root_hz": 349.23,
        "chord": (1.0, 1.26, 1.5),
        "pad_gain": 0.055,
        "melody_gain": 0.70,
        "notes": [(523.25, 0.24), (659.25, 0.26), (783.99, 0.30)],
        "tail_fade_ratio": 0.26,
    },
}

_RENDER_RATE_HQ = 22050
_MASTER_PEAK_TARGET = 0.96


def _piano_bright_wave(t: float, freq_hz: float, env: float) -> float:
    """
    Timbre piano electrique lumineux (stinger corporate).

    @param t Temps dans la note (s).
    @param freq_hz Frequence fondamentale.
    @param env Enveloppe ADSR.
    @returns Echantillon -1..1.
    """
    phase = 2.0 * math.pi * freq_hz * t
    wave_val = math.sin(phase) * 0.55
    wave_val += math.sin(phase * 2.0) * 0.22
    wave_val += math.sin(phase * 3.0) * 0.12
    wave_val += math.sin(phase * 4.5) * 0.06
    decay = math.exp(-t * 4.5)
    return wave_val * env * (0.35 + 0.65 * decay)


def _synth_pluck_wave(t: float, freq_hz: float, env: float) -> float:
    """
    Timbre synth pluck type startup / EDM corporate.

    @param t Temps dans la note (s).
    @param freq_hz Frequence fondamentale.
    @param env Enveloppe ADSR.
    @returns Echantillon -1..1.
    """
    phase = 2.0 * math.pi * freq_hz * t
    saw = 2.0 * ((freq_hz * t) % 1.0 - 0.5)
    wave_val = saw * 0.18 + math.sin(phase) * 0.45
    wave_val += math.sin(phase * 2.01) * 0.15
    decay = math.exp(-t * 6.0)
    return wave_val * env * decay


def _marimba_wave(t: float, freq_hz: float, env: float) -> float:
    """
    Timbre marimba / xylophone chaleureux.

    @param t Temps dans la note (s).
    @param freq_hz Frequence fondamentale.
    @param env Enveloppe ADSR.
    @returns Echantillon -1..1.
    """
    phase = 2.0 * math.pi * freq_hz * t
    wave_val = math.sin(phase) * 0.70
    wave_val += math.sin(phase * 4.0) * 0.18
    decay = math.exp(-t * 8.0)
    return wave_val * env * (0.2 + 0.8 * decay)


def _acoustic_wave(t: float, freq_hz: float, env: float) -> float:
    """
    Timbre guitare acoustique simulee (harmoniques douces).

    @param t Temps dans la note (s).
    @param freq_hz Frequence fondamentale.
    @param env Enveloppe ADSR.
    @returns Echantillon -1..1.
    """
    phase = 2.0 * math.pi * freq_hz * t
    wave_val = math.sin(phase) * 0.50
    wave_val += math.sin(phase * 2.0) * 0.28
    wave_val += math.sin(phase * 3.0) * 0.14
    decay = math.exp(-t * 2.8)
    return wave_val * env * decay


_STINGER_WAVEFORMS: dict[str, object] = {
    "piano": _piano_bright_wave,
    "synth": _synth_pluck_wave,
    "marimba": _marimba_wave,
    "acoustic": _acoustic_wave,
    "bell": _telecom_bell_wave,
}


def _normalize_mix_buffer(mix: list[float], *, peak_target: float = _MASTER_PEAK_TARGET) -> list[float]:
    """
    Normalise un buffer float mono vers un pic cible.

    @param mix Echantillons -1..1.
    @param peak_target Amplitude max cible (0-1).
    @returns Buffer normalise.
    """
    peak = max((abs(v) for v in mix), default=0.0)
    if peak <= 0:
        return mix
    gain = peak_target / peak
    return [v * gain for v in mix]


def _apply_fade_edges(mix: list[float], render_rate: int, *, fade_in_ms: float = 40.0, fade_out_ms: float = 180.0) -> None:
    """
    Applique des fondus entree/sortie sur un buffer en place.

    @param mix Buffer audio.
    @param render_rate Frequence d'echantillonnage.
    @param fade_in_ms Fondu entree en ms.
    @param fade_out_ms Fondu sortie en ms.
    """
    sample_count = len(mix)
    fade_in = max(1, int(render_rate * fade_in_ms / 1000.0))
    fade_out = max(1, int(render_rate * fade_out_ms / 1000.0))
    for i in range(sample_count):
        if i < fade_in:
            mix[i] *= i / float(fade_in)
        elif i > sample_count - fade_out:
            mix[i] *= max(0.0, (sample_count - i) / float(fade_out))


def write_stinger_intro_wav(
    out_path: Path,
    *,
    variant: str = "sting_corporate",
    duration_ms: int = 3200,
) -> None:
    """
    Genere un jingle melodique type stinger corporate (sans pad, niveau fort).

    @param out_path Fichier WAV 8 kHz 8-bit modem.
    @param variant sting_corporate, sting_startup, sting_marimba, etc.
    @param duration_ms Duree maximale en millisecondes.
    """
    spec = _STINGER_SCORES.get(variant) or _STINGER_SCORES["sting_corporate"]
    notes: list[tuple[float, float]] = spec["notes"]
    timbre = str(spec.get("timbre", "piano"))
    wave_fn = _STINGER_WAVEFORMS.get(timbre) or _telecom_bell_wave
    overlap = float(spec.get("overlap", 0.78))
    render_rate = _RENDER_RATE_HQ
    total_note_sec = sum(d for _, d in notes)
    scale = min(1.0, (duration_ms / 1000.0) / max(total_note_sec, 0.1))
    sample_count = max(1, int(render_rate * duration_ms / 1000))
    mix = [0.0] * sample_count
    pos = 0
    for freq, note_sec in notes:
        note_samples = max(1, int(render_rate * note_sec * scale))
        for i in range(note_samples):
            idx = pos + i
            if idx >= sample_count:
                break
            env = _adsr_envelope(i, note_samples, attack_ratio=0.04, release_ratio=0.26)
            t = i / float(render_rate)
            mix[idx] += wave_fn(t, float(freq), env)
        pos += max(1, int(note_samples * overlap))
    mix = _normalize_mix_buffer(mix)
    _apply_fade_edges(mix, render_rate)
    try:
        segment = _mix_buffer_to_segment(mix, render_rate)
    except ImportError:
        write_telecom_voicemail_intro_wav(out_path, variant="sfr_a", duration_ms=duration_ms)
        return
    export_wav_8k_8bit(segment, out_path, normalize=True)


def _pad_wave(t: float, root_hz: float, chord_ratios: tuple[float, ...], env: float) -> float:
    """
    Nappe harmonique douce (fond musical leger).

    @param t Temps en secondes.
    @param root_hz Frequence fondamentale de l'accord.
    @param chord_ratios Ratios harmoniques de l'accord.
    @param env Enveloppe amplitude.
    @returns Echantillon -1..1.
    """
    val = 0.0
    for ratio in chord_ratios:
        freq = root_hz * ratio
        phase = 2.0 * math.pi * freq * t
        val += math.sin(phase) * 0.38
        val += math.sin(phase * 2.005) * 0.08
    return val * env


def _mix_buffer_to_segment(mix: list[float], render_rate: int) -> "AudioSegment":
    """
    Convertit un buffer float mono en AudioSegment pydub.

    @param mix Echantillons -1..1.
    @param render_rate Frequence d'echantillonnage.
    @returns Segment audio mono.
    @raises ImportError Si pydub manque.
    """
    from pydub import AudioSegment

    raw = bytearray()
    for value in mix:
        s16 = int(max(-1.0, min(1.0, value)) * 32767)
        raw.extend(s16.to_bytes(2, "little", signed=True))
    return AudioSegment(data=bytes(raw), sample_width=2, frame_rate=render_rate, channels=1)


def write_greeting_jingle_with_pad_wav(
    out_path: Path,
    *,
    variant: str = "pad_warm",
    duration_ms: int = 3200,
) -> None:
    """
    Genere un jingle court avec fond musical leger + melodie (fondu vers voix prevu).

    @param out_path Fichier WAV 8 kHz 8-bit modem.
    @param variant pad_warm, pad_soft, pad_bright, pad_calm, pad_mini.
    @param duration_ms Duree maximale en millisecondes.
    """
    spec = _PAD_JINGLE_SCORES.get(variant) or _PAD_JINGLE_SCORES["pad_warm"]
    notes: list[tuple[float, float]] = spec["notes"]
    render_rate = _RENDER_RATE_HQ
    total_note_sec = sum(d for _, d in notes)
    scale = min(1.0, (duration_ms / 1000.0) / max(total_note_sec, 0.1))
    sample_count = max(1, int(render_rate * duration_ms / 1000))
    pad_mix = [0.0] * sample_count
    melody_mix = [0.0] * sample_count

    pad_attack = max(1, int(render_rate * 0.18))
    for i in range(sample_count):
        t = i / float(render_rate)
        pad_env = 1.0
        if i < pad_attack:
            pad_env = i / float(pad_attack)
        tail_start = int(sample_count * (1.0 - float(spec.get("tail_fade_ratio", 0.22))))
        if i >= tail_start:
            pad_env *= max(0.0, (sample_count - i) / float(max(1, sample_count - tail_start)))
        pad_mix[i] = _pad_wave(t, float(spec["root_hz"]), tuple(spec["chord"]), pad_env)

    pos = 0
    for freq, note_sec in notes:
        note_samples = max(1, int(render_rate * note_sec * scale))
        for i in range(note_samples):
            idx = pos + i
            if idx >= sample_count:
                break
            env = _adsr_envelope(i, note_samples, attack_ratio=0.05, release_ratio=0.32)
            t = i / float(render_rate)
            melody_mix[idx] += _telecom_bell_wave(t, float(freq), env)
        pos += max(1, int(note_samples * 0.80))

    mix = [
        pad_mix[i] * float(spec["pad_gain"]) + melody_mix[i] * float(spec["melody_gain"])
        for i in range(sample_count)
    ]
    peak = max((abs(v) for v in mix), default=0.0)
    if peak > 0:
        gain = 0.90 / peak
        mix = [v * gain for v in mix]

    fade_in = max(1, int(render_rate * 0.04))
    for i in range(sample_count):
        if i < fade_in:
            mix[i] *= i / float(fade_in)

    try:
        segment = _mix_buffer_to_segment(mix, render_rate)
    except ImportError:
        write_telecom_voicemail_intro_wav(out_path, variant="sfr_a", duration_ms=duration_ms)
        return
    export_wav_8k_8bit(segment, out_path, normalize=True)


def default_bed_variant_for_jingle(jingle_variant: str) -> str:
    """
    Retourne le fond musical sous voix associe a un jingle d'intro.

    @param jingle_variant Identifiant jingle (sting_marimba, ...).
    @returns Identifiant bed (bed_marimba_warm, ...).
    """
    return _JINGLE_DEFAULT_BED.get(jingle_variant, "bed_marimba_warm")


def list_voice_bed_variants() -> list[str]:
    """
    Liste les identifiants de fonds musicaux sous la voix.

    @returns Noms de variantes bed_*.
    """
    return sorted(_VOICE_BED_SCORES.keys())


def voice_bed_label(variant: str) -> str:
    """
    Libelle lisible d'une partition fond sous voix.

    @param variant Identifiant bed_*.
    @returns Libelle ou identifiant brut.
    """
    spec = _VOICE_BED_SCORES.get(variant) or {}
    return str(spec.get("label", variant))


def synthesize_voice_bed_segment(
    duration_ms: int,
    variant: str = "bed_marimba_warm",
) -> "AudioSegment":
    """
    Genere un fond musical compose (pad + arpege doux) pour sous la voix.

    @param duration_ms Duree cible en millisecondes.
    @param variant Identifiant bed_*.
    @returns Segment pydub mono 8 kHz 16-bit interne.
    """
    spec = _VOICE_BED_SCORES.get(variant) or _VOICE_BED_SCORES["bed_marimba_warm"]
    root_hz = float(spec["root_hz"])
    chord = tuple(spec["chord"])
    arp_steps: list[tuple[float, float]] = list(spec.get("arp", [(1.0, 0.5)]))
    timbre = str(spec.get("timbre", "marimba"))
    wave_fn = _STINGER_WAVEFORMS.get(timbre) or _marimba_wave
    pad_gain = float(spec.get("pad_gain", 0.16))
    arp_gain = float(spec.get("arp_gain", 0.36))
    overlap = float(spec.get("loop_overlap", 0.90))
    render_rate = _RENDER_RATE_HQ
    sample_count = max(1, int(render_rate * duration_ms / 1000))
    mix = [0.0] * sample_count

    for i in range(sample_count):
        t = i / float(render_rate)
        mix[i] += _pad_wave(t, root_hz, chord, 1.0) * pad_gain

    pos = 0
    safety = 0
    while pos < sample_count and safety < 500:
        safety += 1
        for ratio, note_sec in arp_steps:
            freq = root_hz * float(ratio)
            note_samples = max(1, int(render_rate * float(note_sec) * 0.52))
            for i in range(note_samples):
                idx = pos + i
                if idx >= sample_count:
                    break
                env = _adsr_envelope(i, note_samples, attack_ratio=0.14, release_ratio=0.38)
                t = i / float(render_rate)
                mix[idx] += wave_fn(t, freq, env) * arp_gain
            pos += max(1, int(note_samples * overlap))

    mix = _normalize_mix_buffer(mix, peak_target=0.52)
    try:
        segment = _mix_buffer_to_segment(mix, render_rate)
    except ImportError:
        from pydub import AudioSegment

        return AudioSegment.silent(duration=duration_ms, frame_rate=MODEM_SAMPLE_RATE)
    return segment.set_channels(1).set_frame_rate(MODEM_SAMPLE_RATE)


def list_greeting_jingle_variants() -> list[str]:
    """
    Liste les identifiants de jingles disponibles.

    @returns Noms de variantes (telecom + pad).
    """
    return sorted(
        set(_STINGER_SCORES.keys())
        | set(_TELECOM_INTRO_SCORES.keys())
        | set(_PAD_JINGLE_SCORES.keys())
    )


def write_greeting_intro_wav(
    out_path: Path,
    *,
    variant: str = "sting_corporate",
    duration_ms: int = 3200,
) -> None:
    """
    Point d'entree unique : stinger, pad legacy ou telecom selon le variant.

    @param out_path Fichier WAV de sortie.
    @param variant Identifiant variante.
    @param duration_ms Duree cible ms.
    """
    if variant in _STINGER_SCORES:
        write_stinger_intro_wav(out_path, variant=variant, duration_ms=duration_ms)
    elif variant in _PAD_JINGLE_SCORES:
        write_greeting_jingle_with_pad_wav(out_path, variant=variant, duration_ms=duration_ms)
    elif variant in _TELECOM_INTRO_SCORES:
        write_telecom_voicemail_intro_wav(out_path, variant=variant, duration_ms=duration_ms)
    else:
        write_stinger_intro_wav(out_path, variant="sting_corporate", duration_ms=duration_ms)


def write_telecom_voicemail_intro_wav(
    out_path: Path,
    *,
    variant: str = "sfr_a",
    duration_ms: int = 3600,
) -> None:
    """
    Genere une intro type messagerie operateur (cloche synthé, composition originale).

    Inspire du style SFR / repondeur mobile : arpège majeur bref, timbre clair,
    optimise pour la bande telephonique 8 kHz.

    @param out_path Fichier WAV de sortie (8 kHz mono 8-bit).
    @param variant Identifiant motif : sfr_a, sfr_b, sfr_c.
    @param duration_ms Duree maximale cible en millisecondes.
    """
    notes = _TELECOM_INTRO_SCORES.get(variant) or _TELECOM_INTRO_SCORES["sfr_a"]
    render_rate = 22050
    total_note_sec = sum(d for _, d in notes)
    scale = min(1.0, (duration_ms / 1000.0) / max(total_note_sec, 0.1))
    sample_count = max(1, int(render_rate * duration_ms / 1000))
    mix = [0.0] * sample_count
    pos = 0
    for freq, note_sec in notes:
        note_samples = max(1, int(render_rate * note_sec * scale))
        for i in range(note_samples):
            idx = pos + i
            if idx >= sample_count:
                break
            env = _adsr_envelope(i, note_samples, attack_ratio=0.06, release_ratio=0.28)
            t = i / float(render_rate)
            mix[idx] += _telecom_bell_wave(t, freq, env)
        pos += max(1, int(note_samples * 0.82))
    mix = _normalize_mix_buffer(mix)
    _apply_fade_edges(mix, render_rate, fade_in_ms=50.0, fade_out_ms=200.0)
    try:
        from pydub import AudioSegment
    except ImportError:
        write_greeting_jingle_wav_8k_legacy(out_path, duration_ms=duration_ms)
        return
    raw = bytearray()
    for value in mix:
        s16 = int(max(-1.0, min(1.0, value)) * 32767)
        raw.extend(s16.to_bytes(2, "little", signed=True))
    segment = AudioSegment(data=bytes(raw), sample_width=2, frame_rate=render_rate, channels=1)
    export_wav_8k_8bit(segment, out_path, normalize=True)


def write_greeting_jingle_wav_8k_legacy(out_path: Path, *, duration_ms: int = 3800) -> None:
    """
    Ancien arpege sine 8 kHz (secours si pydub indisponible).

    @param out_path Fichier WAV de sortie.
    @param duration_ms Duree cible maximale en millisecondes.
    """
    rate = 8000
    notes: list[tuple[float, float]] = [
        (523.25, 0.28),
        (659.25, 0.28),
        (783.99, 0.32),
        (1046.50, 0.45),
    ]
    total_note_sec = sum(d for _, d in notes)
    scale = min(1.0, (duration_ms / 1000.0) / max(total_note_sec, 0.1))
    sample_count = max(1, int(rate * duration_ms / 1000))
    samples = bytearray(sample_count)
    amplitude = 72
    fade = max(1, int(rate * 0.012))
    pos = 0
    for freq, note_sec in notes:
        note_samples = max(1, int(rate * note_sec * scale))
        for i in range(note_samples):
            if pos >= sample_count:
                break
            t = i / rate
            env = _adsr_envelope(i, note_samples)
            wave_val = _telecom_bell_wave(t, freq, env)
            value = 128 + int(amplitude * wave_val)
            samples[pos] = max(0, min(255, value))
            pos += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(rate)
        wf.writeframes(bytes(samples))


def write_greeting_jingle_wav_8k(out_path: Path, *, duration_ms: int = 3800, variant: str = "sting_corporate") -> None:
    """
    Genere l'intro messagerie par defaut (pad musical ou telecom).

    @param out_path Fichier WAV de sortie.
    @param duration_ms Duree cible maximale en millisecondes.
    @param variant Motif pad_* ou sfr_*.
    """
    write_greeting_intro_wav(out_path, variant=variant, duration_ms=duration_ms)


def pcm_u8_chunk_peak(raw: bytes) -> int:
    """
    Pic d'amplitude d'un bloc PCM 8-bit centré sur 128 (0 = silence).

    @param raw Octets audio bruts du flux VRX.
    @returns Écart maximal par rapport au silence (0-127).
    """
    if not raw:
        return 0
    peak = 0
    for byte in raw:
        deviation = abs(byte - 128)
        if deviation > peak:
            peak = deviation
    return peak


def trim_leading_trailing_silence(
    segment: "AudioSegment",
    *,
    silence_threshold: float = -40.0,
    chunk_size: int = 10,
    padding_ms: int = 30,
) -> "AudioSegment":
    """
    Retire le silence au debut et a la fin (compatible pydub sans strip_silence).
    """
    from pydub.silence import detect_leading_silence

    if len(segment) <= 0:
        return segment
    start = detect_leading_silence(
        segment, silence_threshold=silence_threshold, chunk_size=chunk_size
    )
    end = detect_leading_silence(
        segment.reverse(), silence_threshold=silence_threshold, chunk_size=chunk_size
    )
    start = max(0, start - padding_ms)
    end = max(0, end - padding_ms)
    duration = len(segment)
    if start + end >= duration:
        return segment
    return segment[start : duration - end]


def load_audio_segment_modem(segment_path: Path) -> "AudioSegment":
    """
    Charge un fichier audio en mono 8 kHz 16-bit pour traitement modem.

    @param segment_path Fichier source.
    @returns Segment pydub pret pour mixage.
    @raises ImportError Si pydub manque.
    """
    from pydub import AudioSegment

    segment = AudioSegment.from_file(str(segment_path))
    segment = segment.set_channels(1)
    if segment.frame_rate != MODEM_SAMPLE_RATE:
        if _ffmpeg_available():
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_in = Path(tmp.name)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp2:
                tmp_out = Path(tmp2.name)
            try:
                segment.export(str(tmp_in), format="wav")
                ffmpeg_convert_to_modem_wav(tmp_in, tmp_out, normalize=False)
                segment = AudioSegment.from_file(str(tmp_out))
                return segment.set_channels(1).set_sample_width(2)
            finally:
                for p in (tmp_in, tmp_out):
                    try:
                        p.unlink(missing_ok=True)
                    except OSError:
                        pass
        segment = segment.set_frame_rate(MODEM_SAMPLE_RATE)
    return segment.set_sample_width(2)


def segment_to_modem_pcm_u8(segment: "AudioSegment", *, normalize: bool = True) -> bytes:
    """
    Convertit un segment mono 8 kHz en PCM 8-bit non signe (128 = silence).

    @param segment Audio pydub (sera force en mono 8 kHz).
    @param normalize Normalise le niveau avant conversion 8-bit.
    @returns Octets PCM pour VTX modem.
    """
    segment = segment.set_channels(1).set_frame_rate(MODEM_SAMPLE_RATE)
    if normalize:
        peak = segment.max or 0
        if peak > 0:
            target = 26000.0
            gain_db = 20.0 * math.log10(target / float(peak))
            if abs(gain_db) > 0.05:
                segment = segment.apply_gain(gain_db)
    raw = segment.raw_data
    samples = bytearray()
    for i in range(0, len(raw), 2):
        s16 = int.from_bytes(raw[i : i + 2], "little", signed=True)
        u8 = int(round((s16 / 32768.0) * 127.0 + 128.0))
        samples.append(max(0, min(255, u8)))
    return bytes(samples)


def wav_path_to_modem_pcm_u8(wav_path: Path, *, normalize: bool = True) -> bytes:
    """
    Lit un fichier audio et retourne du PCM 8 kHz 8-bit pour lecture modem.

    Les WAV deja au format modem (8 kHz mono u8) sont lus directement sans re-conversion.

    @param wav_path Chemin vers le fichier.
    @param normalize Normalise le niveau audio si reconversion necessaire.
    @returns Buffer PCM pret pour VTX.
    """
    with wave.open(str(wav_path), "rb") as wf:
        rate = wf.getframerate()
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        if rate == MODEM_SAMPLE_RATE and channels == 1 and width == 1:
            raw = wf.readframes(wf.getnframes())
            if normalize:
                return normalize_pcm_u8_buffer(raw)
            return raw

    if _ffmpeg_available():
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_out = Path(tmp.name)
        try:
            ffmpeg_convert_to_modem_wav(wav_path, tmp_out, normalize=normalize)
            with wave.open(str(tmp_out), "rb") as wf:
                return wf.readframes(wf.getnframes())
        finally:
            try:
                tmp_out.unlink(missing_ok=True)
            except OSError:
                pass

    segment = load_audio_segment_modem(wav_path)
    return segment_to_modem_pcm_u8(segment, normalize=normalize)


def export_wav_8k_8bit(segment: "AudioSegment", out_path: Path, *, normalize: bool = False) -> None:
    """
    Exporte un AudioSegment en WAV 8 kHz, mono, 8-bit non signé.
    Format attendu par le modem Conexant (mode voix série) et IVR téléphone.

    Utilise ffmpeg/soxr si disponible pour un resampling propre (meilleure qualite voix).

    Args:
        segment: Segment pydub (peut être 16-bit, autre rate).
        out_path: Fichier WAV de sortie.
        normalize: Normalisation douce avant conversion 8-bit.
    """
    segment = segment.set_channels(1)
    if normalize:
        segment = normalize_segment_peak(segment)

    if _ffmpeg_available():
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            segment.export(str(tmp_path), format="wav")
            ffmpeg_convert_to_modem_wav(tmp_path, out_path, normalize=False)
            return
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    segment = segment.set_frame_rate(MODEM_SAMPLE_RATE)
    raw = segment.raw_data
    samples_8 = bytearray()
    for i in range(0, len(raw), 2):
        s16 = int.from_bytes(raw[i : i + 2], "little", signed=True)
        u8 = int(round((s16 / 32768.0) * 127.0 + 128.0))
        samples_8.append(max(0, min(255, u8)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(MODEM_SAMPLE_RATE)
        wf.writeframes(bytes(samples_8))


def export_listen_preview_wav(
    source_path: Path,
    out_path: Path,
    *,
    sample_rate: int = 44100,
    target_peak: float = 30000.0,
) -> Path:
    """
    Exporte un WAV modem en version ecoute PC : 44.1 kHz, 16-bit, niveau fort.

    @param source_path WAV source (modem ou autre).
    @param out_path Fichier WAV de sortie pour ecoute locale.
    @param sample_rate Frequence cible (defaut 44100).
    @param target_peak Pic amplitude 16-bit cible (~30000 = -1 dBFS).
    @returns Chemin du fichier genere.
    @raises ImportError Si pydub/ffmpeg manque.
    """
    output_path = Path(out_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if _ffmpeg_available():
        filters = (
            f"aresample=resampler=soxr:osr={sample_rate}:precision=28:cheby=1,"
            f"volume=3dB"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-af",
            filters,
            "-sample_fmt",
            "s16",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            return output_path

    from pydub import AudioSegment

    segment = AudioSegment.from_file(str(source_path))
    segment = segment.set_channels(1).set_frame_rate(sample_rate).set_sample_width(2)
    peak = segment.max or 0
    if peak > 0:
        gain_db = 20.0 * math.log10(target_peak / float(peak))
        if abs(gain_db) > 0.05:
            segment = segment.apply_gain(gain_db)
    segment.export(str(output_path), format="wav", parameters=["-ac", "1"])
    return output_path


def combine_modem_wav_files(
    paths: list[Path],
    out_path: Path,
    *,
    gap_ms: int = 350,
    max_first_ms: Optional[int] = None,
    normalize: bool = True,
) -> Path:
    """
    Concatene plusieurs fichiers audio en un seul WAV 8 kHz 8-bit (lecture fluide modem).

    @param paths Fichiers a enchainer (intro puis message vocal, etc.).
    @param out_path Fichier WAV de sortie.
    @param gap_ms Silence entre les morceaux.
    @param max_first_ms Duree max du premier morceau (intro).
    @param normalize Normalise le niveau final.
    @returns Chemin du WAV genere.
    """
    from pydub import AudioSegment

    if not paths:
        raise ValueError("combine_modem_wav_files: liste vide")
    combined = AudioSegment.empty()
    gap = AudioSegment.silent(duration=max(0, gap_ms), frame_rate=MODEM_SAMPLE_RATE)
    for index, path in enumerate(paths):
        if not path.is_file():
            continue
        piece = load_audio_segment_modem(path)
        piece = trim_leading_trailing_silence(piece, padding_ms=20)
        if index == 0 and max_first_ms is not None and max_first_ms > 0:
            piece = piece[:max_first_ms]
            piece = piece.fade_out(min(600, max(80, len(piece) // 8)))
        if len(combined) > 0 and len(piece) > 0:
            combined += gap
        combined += piece
    export_wav_8k_8bit(combined, out_path, normalize=normalize)
    return out_path


def crossfade_audio_segments(
    intro: "AudioSegment",
    voice: "AudioSegment",
    *,
    crossfade_ms: int = 500,
    voice_bed_gain_db: Optional[float] = None,
    voice_mix_gain_db: float = 5.0,
    intro_duck_db: float = 6.0,
    voice_bed_variant: str = "bed_marimba_warm",
) -> "AudioSegment":
    """
    Fondu enchaine intro musicale -> voix, avec fond musical leger sous l'annonce.

    @param intro Segment intro (jingle).
    @param voice Segment voix TTS.
    @param crossfade_ms Duree du fondu en millisecondes.
    @param voice_bed_gain_db Niveau du fond sous la voix (dB negatif, None ou 0 = sans fond).
    @param voice_mix_gain_db Gain supplementaire sur la voix (dB).
    @param intro_duck_db Attenuation du jingle pendant le fondu.
    @param voice_bed_variant Partition fond musical compose (bed_*).
    @returns Segment concatene avec chevauchement.
    """
    from pydub import AudioSegment

    if len(intro) <= 0:
        return voice
    if len(voice) <= 0:
        return intro
    cf = min(max(80, int(crossfade_ms)), len(intro) - 20, len(voice))
    if cf <= 0:
        return intro + voice
    head = intro[:-cf]
    tail = intro[-cf:].fade_out(cf)
    if intro_duck_db > 0:
        tail = tail - float(intro_duck_db)
    fade_in_ms = min(cf, max(100, cf // 2))
    voice_in = voice[:cf].fade_in(fade_in_ms)
    if voice_mix_gain_db:
        voice_in = voice_in + float(voice_mix_gain_db)
    voice_rest = voice[cf:]
    if voice_mix_gain_db:
        voice_rest = voice_rest + float(voice_mix_gain_db)
    cross_part = tail.overlay(voice_in)

    use_bed = voice_bed_gain_db is not None and float(voice_bed_gain_db) < -1.0
    if use_bed and len(voice_rest) > 0:
        bed = _build_voice_music_bed(
            len(voice_rest),
            gain_db=float(voice_bed_gain_db),
            bed_variant=voice_bed_variant,
        )
        voice_with_bed = bed.overlay(voice_rest)
        return head + cross_part + voice_with_bed

    return head + cross_part + voice_rest


def _segment_dbfs_safe(segment: "AudioSegment", default: float = -40.0) -> float:
    """
    Retourne le niveau dBFS d'un segment, avec valeur de repli si silence.

    @param segment Segment audio pydub.
    @param default Valeur si segment muet ou trop faible.
    @returns Niveau dBFS estime.
    """
    db = segment.dBFS
    if db == float("-inf") or db < -80.0:
        return default
    return float(db)


def recommended_track_solo_gain_db(solo_chunk: "AudioSegment", *, target_dbfs: float = -20.0) -> float:
    """
    Calcule le gain a appliquer sur la partie solo de la piste (intro avant voix).

    @param solo_chunk Extrait musical joue seul avant l'annonce.
    @param target_dbfs Niveau cible dBFS pour l'ecoute telephone.
    @returns Gain en dB (positif si la piste est trop faible).
    """
    current = _segment_dbfs_safe(solo_chunk, -35.0)
    gain = target_dbfs - current
    return max(-4.0, min(22.0, gain))


def recommended_track_duck_db(
    music_under: "AudioSegment",
    voice: "AudioSegment",
    *,
    target_gap_db: float = 15.0,
) -> float:
    """
    Calcule l'attenuation de la musique sous la voix pour garder l'annonce lisible.

    @param music_under Extrait musical qui passera sous la voix.
    @param voice Segment voix normalise.
    @param target_gap_db Ecart cible voix/musique en dB.
    @returns Attenuation musicale en dB (valeur positive a soustraire).
    """
    voice_db = _segment_dbfs_safe(voice, -18.0)
    music_db = _segment_dbfs_safe(music_under, -28.0)
    duck = music_db - (voice_db - target_gap_db)
    return max(10.0, min(24.0, duck))


def _slice_to_modem_segment(raw: "AudioSegment") -> "AudioSegment":
    """
    Convertit un segment pydub arbitraire en mono 8 kHz 16-bit (pipeline modem HQ).

    @param raw Segment source (tout format/rate).
    @returns Segment pret pour mixage modem.
    """
    import tempfile

    from pydub import AudioSegment

    raw = raw.set_channels(1)
    if raw.frame_rate == MODEM_SAMPLE_RATE and raw.sample_width == 2:
        return raw
    if _ffmpeg_available():
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_in:
            tmp_in_path = Path(tmp_in.name)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_out:
            tmp_out_path = Path(tmp_out.name)
        try:
            raw.export(str(tmp_in_path), format="wav")
            ffmpeg_convert_to_modem_wav(tmp_in_path, tmp_out_path, normalize=False)
            return AudioSegment.from_file(str(tmp_out_path)).set_channels(1).set_sample_width(2)
        finally:
            for path in (tmp_in_path, tmp_out_path):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
    return raw.set_frame_rate(MODEM_SAMPLE_RATE).set_sample_width(2)


def combine_music_track_voice_overlay(
    music_path: Path,
    voice_path: Path,
    out_path: Path,
    *,
    music_solo_ms: int = 2000,
    music_offset_ms: int = 0,
    voice_fade_ms: int = 450,
    music_duck_db: Optional[float] = None,
    music_solo_gain_db: Optional[float] = None,
    voice_mix_gain_db: float = 4.0,
    music_tail_ms: int = 450,
    music_fade_out_ms: int = 650,
) -> Path:
    """
    Joue le debut d'une piste musicale, puis superpose l'annonce vocale sans couper la musique.

    La musique continue sous la voix avec un ducking automatique calibre sur les niveaux reels.

    @param music_path Fichier musical (MP3/WAV).
    @param voice_path Message vocal TTS (WAV modem).
    @param out_path WAV combine 8 kHz 8-bit.
    @param music_solo_ms Duree musicale seule avant le debut de la voix.
    @param music_offset_ms Point de depart dans la piste source.
    @param voice_fade_ms Fondu entree de la voix sur la musique.
    @param music_duck_db Attenuation musique sous voix (None ou 0 = auto).
    @param music_solo_gain_db Boost intro solo (None = auto selon RMS).
    @param voice_mix_gain_db Gain supplementaire sur la voix.
    @param music_tail_ms Queue musicale apres la voix.
    @param music_fade_out_ms Fondu sortie musical final.
    @returns Chemin WAV genere.
  """
    from pydub import AudioSegment

    voice = load_audio_segment_modem(voice_path)
    voice = trim_leading_trailing_silence(voice, padding_ms=15, silence_threshold=-48.0)
    voice = normalize_segment_peak(voice)
    if len(voice) <= 0:
        raise ValueError("segment voix vide")

    solo_ms = max(0, int(music_solo_ms))
    tail_ms = max(120, int(music_tail_ms))
    offset_ms = max(0, int(music_offset_ms))
    total_raw_ms = offset_ms + max(solo_ms, 0) + len(voice) + tail_ms + 800

    raw_music = AudioSegment.from_file(str(music_path)).set_channels(1)
    if offset_ms >= len(raw_music):
        raise ValueError("offset musical hors piste")
    raw_slice = raw_music[offset_ms:min(len(raw_music), total_raw_ms)]
    music = _slice_to_modem_segment(raw_slice)
    min_music_ms = solo_ms + len(voice) + 80
    if len(music) < min_music_ms:
        raise ValueError("extrait musical trop court pour le mix")

    if solo_ms > 0:
        solo_part = music[:solo_ms]
        if music_solo_gain_db is None:
            music_solo_gain_db = recommended_track_solo_gain_db(solo_part)
        if music_solo_gain_db:
            music = music + float(music_solo_gain_db)
            solo_part = music[:solo_ms]
    else:
        solo_part = AudioSegment.silent(duration=0, frame_rate=MODEM_SAMPLE_RATE)
        level_ref = music[: min(len(music), 2000)]
        if music_solo_gain_db is None:
            # Sans intro solo : eviter de booster la piste (sinon voix noyee / grésillement 8 kHz).
            music_solo_gain_db = recommended_track_solo_gain_db(level_ref, target_dbfs=-26.0)
            music_solo_gain_db = min(float(music_solo_gain_db), 4.0)
        if music_solo_gain_db:
            music = music + float(music_solo_gain_db)

    under_voice = music[solo_ms : solo_ms + len(voice)]
    if len(under_voice) < len(voice):
        pad = AudioSegment.silent(duration=len(voice) - len(under_voice), frame_rate=MODEM_SAMPLE_RATE)
        under_voice = under_voice + pad

    effective_duck = float(music_duck_db or 0.0)
    if effective_duck <= 0.5:
        gap_db = 20.0 if solo_ms <= 0 else 15.0
        effective_duck = recommended_track_duck_db(under_voice, voice, target_gap_db=gap_db)
    under_voice = under_voice - effective_duck

    fade_ms = min(max(120, int(voice_fade_ms)), len(voice), len(under_voice))
    if solo_ms <= 0:
        fade_ms = min(max(fade_ms, 500), len(voice), len(under_voice))
    voice_overlay = voice.fade_in(fade_ms)
    effective_voice_gain = float(voice_mix_gain_db or 0.0)
    if solo_ms <= 0:
        effective_voice_gain = min(effective_voice_gain, 2.0)
    if effective_voice_gain:
        voice_overlay = voice_overlay + effective_voice_gain
    mixed = under_voice.overlay(voice_overlay)

    tail_start = solo_ms + len(voice)
    tail_end = min(len(music), tail_start + tail_ms)
    if tail_end > tail_start:
        tail = music[tail_start:tail_end] - max(6.0, effective_duck * 0.55)
        tail = tail.fade_out(min(music_fade_out_ms, len(tail)))
        combined = solo_part + mixed + tail
    else:
        combined = solo_part + mixed

    combined = limit_segment_peak(combined)
    export_wav_8k_8bit(combined, out_path, normalize=False)
    return out_path


def _build_voice_music_bed(
    duration_ms: int,
    *,
    gain_db: float = -24.0,
    bed_variant: str = "bed_marimba_warm",
) -> "AudioSegment":
    """
    Construit un fond musical compose sous la voix (partition bed_*).

    @param duration_ms Duree cible du fond en millisecondes.
    @param gain_db Attenuation du fond (dB, ex. -24).
    @param bed_variant Identifiant partition fond (bed_marimba_warm, ...).
    @returns Segment fond musical mono 8 kHz.
    """
    from pydub import AudioSegment

    if duration_ms <= 0:
        return AudioSegment.silent(duration=0, frame_rate=MODEM_SAMPLE_RATE)

    bed = synthesize_voice_bed_segment(duration_ms, bed_variant)
    fade_out_ms = min(450, max(150, duration_ms // 5))
    bed = bed.fade_in(100).fade_out(fade_out_ms)
    return bed + float(gain_db)


def combine_intro_voice_crossfade(
    intro_path: Path,
    voice_path: Path,
    out_path: Path,
    *,
    crossfade_ms: int = 500,
    intro_max_ms: Optional[int] = None,
    intro_variant: str = "sting_marimba",
    normalize: bool = True,
    voice_bed_gain_db: Optional[float] = None,
    voice_mix_gain_db: float = 5.0,
    voice_bed_variant: Optional[str] = None,
) -> Path:
    """
    Assemble intro + message vocal avec fondu (modem 8 kHz 8-bit).

    @param intro_path Jingle d'accueil.
    @param voice_path Message TTS.
    @param out_path WAV combine.
    @param crossfade_ms Fondu musique -> voix en ms.
    @param intro_max_ms Duree max intro avant fondu.
    @param intro_variant Variante jingle (pour rogner a la fin du motif).
    @param normalize Normalise le niveau final.
    @param voice_bed_gain_db Fond musical leger sous la voix (dB negatif).
    @param voice_mix_gain_db Gain supplementaire voix (dB).
    @param voice_bed_variant Partition fond compose (bed_*), auto si None.
    @returns Chemin WAV genere.
    """
    bed_variant = voice_bed_variant or default_bed_variant_for_jingle(intro_variant)
    intro = load_audio_segment_modem(intro_path)
    voice = load_audio_segment_modem(voice_path)
    intro = trim_intro_for_voice_handoff(intro)
    cap_ms = int(intro_max_ms or len(intro))
    melody_end_ms = estimated_jingle_melody_end_ms(intro_variant, cap_ms)
    handoff_ms = min(len(intro), melody_end_ms, cap_ms)
    if handoff_ms > 80:
        intro = intro[:handoff_ms]

    voice = trim_leading_trailing_silence(voice, padding_ms=15, silence_threshold=-48.0)
    voice = normalize_segment_peak(voice)

    effective_cf = min(int(crossfade_ms), max(120, handoff_ms // 3), len(intro) - 20, len(voice))
    combined = crossfade_audio_segments(
        intro,
        voice,
        crossfade_ms=effective_cf,
        voice_bed_gain_db=voice_bed_gain_db,
        voice_mix_gain_db=voice_mix_gain_db,
        voice_bed_variant=bed_variant,
    )
    export_wav_8k_8bit(combined, out_path, normalize=False)
    return out_path


def load_wav_as_16k16bit_pcm(wav_path: Path) -> bytes:
    """
    Charge un fichier WAV (8 kHz 8-bit ou 16 kHz 16-bit) et retourne des bytes
    PCM 16-bit mono 16 kHz pour la reconnaissance vocale (VOSK/Whisper).

    Args:
        wav_path: Chemin vers le fichier WAV.

    Returns:
        Données PCM 16-bit little-endian, 16 kHz, mono.
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError("pydub requis: pip install pydub")

    segment = AudioSegment.from_file(str(wav_path))
    segment = segment.set_frame_rate(16000).set_channels(1)
    return segment.raw_data


def has_alsa_capture_devices() -> bool:
    """
    True si `arecord -l` liste au moins un peripherique de capture (carte son / modem ALSA).
    Sur Pi + USR5637 sans carte capture, la section CAPTURE est vide : preferer VRX serie.
    """
    try:
        r = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        out = r.stdout or ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    in_capture_section = False
    for line in out.splitlines():
        if "CAPTURE" in line.upper() and "HARDWARE" in line.upper():
            in_capture_section = True
            continue
        if in_capture_section and re.match(r"^\s*card\s+\d+:", line, re.I):
            return True
    return False


def pcm_u8_8k_to_s16le_16k(data: bytes) -> bytes:
    """
    PCM modem 8 kHz 8-bit unsigned -> PCM 16 kHz 16-bit LE.

    Interpolation lineaire entre echantillons (moins d'aliasing qu'une duplication brute).
    """
    if not data:
        return b""
    out = bytearray()
    n = len(data)
    for i in range(n):
        s0 = (int(data[i]) - 128) * 256
        s1 = (int(data[i + 1]) - 128) * 256 if i + 1 < n else s0
        mid = (s0 + s1) // 2
        s0 = max(-32768, min(32767, s0))
        mid = max(-32768, min(32767, mid))
        out.extend(s0.to_bytes(2, "little", signed=True))
        out.extend(mid.to_bytes(2, "little", signed=True))
    return bytes(out)


def pcm_s16le_16k_mono_to_u8_8k(data: bytes) -> bytes:
    """
    Sous-echantillonne 16 kHz s16le mono vers 8 kHz 8-bit unsigned.

    Moyenne de 2 echantillons consecutifs (anti-alias leger) au lieu de prendre 1 sur 2.
    """
    out = bytearray()
    for i in range(0, len(data) - 3, 4):
        s0 = int.from_bytes(data[i : i + 2], "little", signed=True)
        s1 = int.from_bytes(data[i + 2 : i + 4], "little", signed=True)
        avg = (s0 + s1) // 2
        u8 = max(0, min(255, (avg >> 8) + 128))
        out.append(u8)
    return bytes(out)


def pcm_s16le_rms(data: bytes) -> float:
    """
    RMS d'un buffer PCM s16le mono (valeur 0..32767 environ).

    Utilise pour VAD : ne pas ouvrir VTX sur du silence (evite de saccader l'ecoute ligne).
    """
    if not data or len(data) < 2:
        return 0.0
    n = len(data) // 2
    if n <= 0:
        return 0.0
    acc = 0.0
    for i in range(0, n * 2, 2):
        s = int.from_bytes(data[i : i + 2], "little", signed=True)
        acc += float(s) * float(s)
    return (acc / float(n)) ** 0.5


def write_stereo_u8_8k_wav(path: Path, line_track: bytes, mic_track: bytes) -> None:
    """
    WAV stéréo 8 kHz 8-bit : canal gauche = ligne (VRX), canal droit = micro (VTX).
    Piste la plus courte est complétée par silence (128).
    """
    n = max(len(line_track), len(mic_track))
    if n == 0:
        return
    silence = 128
    line = line_track.ljust(n, bytes([silence]))
    mic = mic_track.ljust(n, bytes([silence]))
    stereo = bytearray(n * 2)
    for i in range(n):
        stereo[i * 2] = line[i]
        stereo[i * 2 + 1] = mic[i]
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(1)
        wf.setframerate(8000)
        wf.writeframes(bytes(stereo))
