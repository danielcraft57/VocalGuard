"""
Profils audio modem (USR5637 vs Conexant).

USR5637 prod : AT+VSM=129,11025 (PCM 16-bit LE @ 11 025 Hz), baud 230400.
Rollback : AT+VSM=128,8000 (8-bit @ 8 kHz), baud 115200.
Conexant / Zoom : AT+VSM=1,8000,0,0, 8-bit @ 8 kHz, baud 115200.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ModemVoiceProfile:
    """Parametres PCM / AT+VSM pour un type de modem."""

    name: str
    sample_rate: int
    sample_width: int
    vsm_command: str
    baudrate: int
    ffmpeg_codec: str

    @property
    def bytes_per_sec(self) -> int:
        """Debit PCM brut (octets / s) sur le flux VTX/VRX."""
        return int(self.sample_rate) * int(self.sample_width)

    @property
    def is_s16(self) -> bool:
        """True si PCM 16-bit."""
        return self.sample_width == 2

    @property
    def vtx_chunk_bytes(self) -> int:
        """Taille de tranche VTX (~40 ms) alignee sur un echantillon."""
        raw = max(self.sample_width, int(round(self.bytes_per_sec * 0.04)))
        return raw - (raw % self.sample_width)

    def silence_threshold_from_u8(self, u8_threshold: int) -> int:
        """
        Convertit un seuil peak u8 (0-127) vers le format du profil.

        @param u8_threshold Seuil historique Conexant / 8-bit.
        @returns Seuil comparable pour pcm_chunk_peak.
        """
        if self.sample_width <= 1:
            return max(1, int(u8_threshold))
        return max(256, int(u8_threshold) * 256)


USR_VOICE_PROFILE = ModemVoiceProfile(
    name="usr5637",
    sample_rate=11025,
    sample_width=2,
    vsm_command="AT+VSM=129,11025",
    baudrate=230400,
    ffmpeg_codec="pcm_s16le",
)

USR_FALLBACK_PROFILE = ModemVoiceProfile(
    name="usr5637_u8",
    sample_rate=8000,
    sample_width=1,
    vsm_command="AT+VSM=128,8000",
    baudrate=115200,
    ffmpeg_codec="pcm_u8",
)

CONEXANT_VOICE_PROFILE = ModemVoiceProfile(
    name="conexant",
    sample_rate=8000,
    sample_width=1,
    vsm_command="AT+VSM=1,8000,0,0",
    baudrate=115200,
    ffmpeg_codec="pcm_u8",
)


def parse_vsm_spec(spec: Optional[str]) -> Optional[ModemVoiceProfile]:
    """
    Interprete une spec config (ex. ``129,11025`` ou ``AT+VSM=128,8000``).

    @param spec Valeur YAML / env ``modem_voice_vsm``.
    @returns Profil USR correspondant, ou None pour garder le defaut.
    """
    raw = (spec or "").strip().upper().replace(" ", "")
    if not raw:
        return None
    if raw.startswith("AT+VSM="):
        raw = raw[7:]
    if raw in ("128,8000", "128"):
        return USR_FALLBACK_PROFILE
    if raw in ("129,11025", "129"):
        return USR_VOICE_PROFILE
    return None


def resolve_profile_from_config(config: object) -> ModemVoiceProfile:
    """
    Profil voix depuis la config applicative (modem_voice_vsm).

    @param config Objet Config (modem_voice_vsm).
    @returns Profil USR 11 kHz ou fallback 8 kHz u8.
    """
    spec = getattr(config, "modem_voice_vsm", None)
    return parse_vsm_spec(spec) or USR_VOICE_PROFILE


def resolve_voice_profile(*, is_conexant: bool, vsm_spec: Optional[str] = None) -> ModemVoiceProfile:
    """
    Choisit le profil voix selon le chipset et un override config.

    @param is_conexant True si ATI a vu un Conexant / Zoom.
    @param vsm_spec Override USR (rollback 128,8000).
    @returns Profil actif.
    """
    if is_conexant:
        return CONEXANT_VOICE_PROFILE
    override = parse_vsm_spec(vsm_spec)
    return override or USR_VOICE_PROFILE
