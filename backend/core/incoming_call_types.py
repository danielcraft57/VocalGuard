"""
Types et modeles Pydantic pour la configuration des appels entrants.

Inspire de Call Attendant (profils permitted / screened / blocked) avec actions composables.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

IncomingAction = Literal[
    "ignore",
    "answer",
    "greeting",
    "record",
    "dtmf_gate",
    "hangup",
    "play_blocked",
]

IncomingProfileName = Literal["permitted", "screened", "blocked"]
IncomingLineMode = Literal["voicemail", "phone"]
WhitelistMatchMode = Literal["exact", "prefix", "e164_normalize"]
AudioSource = Literal["tts", "wav"]
RecordBeepMode = Literal["wav", "dtmf", "none"]
GreetingIntroMode = Literal["none", "jingle", "wav", "track"]


class IncomingProfileConfig(BaseModel):
  """Surcharge optionnelle d'un profil appelant (null = herite du preset actif)."""

  rings_before_answer: Optional[int] = Field(None, ge=0, le=20)
  actions: Optional[List[IncomingAction]] = None
  seize_on_ring: Optional[bool] = None
  require_cid_before_action: Optional[bool] = None


class IncomingCallPresetConfig(BaseModel):
  """Preset global (repondeur ou telephone) appliquant des valeurs par profil."""

  label: str = ""
  permitted_actions: List[IncomingAction] = Field(default_factory=lambda: ["ignore"])
  screened_actions: List[IncomingAction] = Field(
      default_factory=lambda: ["answer", "greeting", "record"]
  )
  blocked_actions: List[IncomingAction] = Field(
      default_factory=lambda: ["answer", "greeting", "hangup"]
  )
  permitted_rings: int = Field(default=0, ge=0, le=20)
  screened_rings: int = Field(default=0, ge=0, le=20)
  blocked_rings: int = Field(default=0, ge=0, le=20)


class IncomingCallAdvancedConfig(BaseModel):
  """Reglages experts (abort parallele, retry accueil, etc.)."""

  abort_answer_if_parallel_pickup: bool = True
  blocked_play_message: bool = True
  blocked_message_max_sec: float = Field(default=5.0, ge=0.5, le=60.0)
  retry_greeting_on_fail: bool = True
  prepare_voice_after_seize: bool = True


class IncomingCallAudioConfig(BaseModel):
  """Sources audio pour accueil, message bloque et bip."""

  greeting_source: AudioSource = "tts"
  greeting_wav_path: Optional[str] = None
  blocked_source: AudioSource = "wav"
  blocked_wav_path: Optional[str] = "resources/voice/system/blocked_short.wav"
  blocked_tts_text: Optional[str] = None
  record_beep: RecordBeepMode = "wav"
  record_beep_wav_path: Optional[str] = "resources/voice/system/beep.wav"
  edge_tts_rate: str = "+0%"
  edge_tts_voice: str = "fr-FR-VivienneMultilingualNeural"
  edge_tts_pitch: str = "+7Hz"
  greeting_intro_mode: GreetingIntroMode = "jingle"
  greeting_intro_variant: str = "sting_marimba"
  greeting_intro_wav_path: Optional[str] = "resources/voice/intros/default.wav"
  greeting_intro_sec: float = Field(default=2.2, ge=0.0, le=20.0)
  greeting_intro_crossfade_ms: int = Field(default=280, ge=100, le=2000)
  greeting_intro_voice_gain_db: float = Field(
      default=5.0,
      ge=0.0,
      le=12.0,
      description="Gain supplementaire voix d'accueil sur le jingle (dB).",
  )
  greeting_intro_voice_bed_db: float = Field(
      default=-24.0,
      ge=-40.0,
      le=0.0,
      description="Niveau du fond musical sous la voix (dB, 0=desactive).",
  )
  greeting_intro_bed_variant: Optional[str] = None
  greeting_intro_track_duck_db: float = Field(
      default=0.0,
      ge=0.0,
      le=28.0,
      description="Attenuation musique sous la voix en mode track (0 = auto).",
  )
  greeting_intro_music_offset_sec: float = Field(
      default=0.0,
      ge=0.0,
      le=120.0,
      description="Point de depart dans la piste musicale (secondes).",
  )
  greeting_tts_text: Optional[str] = (
      "Bonjour, Monsieur Daniel est absent. Merci de laisser un message apres le bip."
  )


class IncomingVoicemailConfig(BaseModel):
  """Messagerie vocale et filtre DTMF anti-robots."""

  require_dtmf: bool = False
  dtmf_digit: str = Field(default="1", min_length=1, max_length=1)
  dtmf_prompt_source: AudioSource = "tts"
  dtmf_prompt_text: str = "Tapez 1 pour laisser un message."
  dtmf_timeout_sec: float = Field(default=8.0, ge=2.0, le=30.0)
  max_record_sec: int = Field(default=120, ge=10, le=600)
  silence_end_sec: float = Field(default=4.0, ge=1.0, le=30.0)


class IncomingNumberPatternRule(BaseModel):
  """Regle de pattern numerique (ex. +338%, masque P)."""

  pattern: str = Field(..., min_length=1, max_length=64)
  action: IncomingProfileName = "blocked"
  reason: str = ""
  enabled: bool = True


class IncomingNumberPatternsConfig(BaseModel):
  """Liste de patterns numeriques."""

  enabled: bool = True
  rules: List[IncomingNumberPatternRule] = Field(default_factory=list)


class IncomingCallSettingsData(BaseModel):
  """
  Configuration persistee des appels entrants (data/incoming_call_settings.yaml).

  Les champs plats sont aussi synchronises sur l'objet Config runtime.
  """

  cid_wait_sec: float = Field(default=2.5, ge=0.0, le=30.0)
  instant_seize_cid_grace_sec: float = Field(default=0.35, ge=0.0, le=5.0)
  ring_cycle_sec: float = Field(default=6.0, ge=3.0, le=15.0)
  ring_quiet_abort_sec: float = Field(default=6.0, ge=2.0, le=20.0)
  max_incoming_wait_sec: float = Field(default=45.0, ge=10.0, le=120.0)
  phone_mode_rings: int = Field(default=4, ge=0, le=20)
  whitelist_ring_only: bool = False
  whitelist_match: WhitelistMatchMode = "exact"
  screened_when_unknown: bool = True
  active_preset: IncomingLineMode = "voicemail"
  presets: Dict[str, IncomingCallPresetConfig] = Field(default_factory=dict)
  profiles: Dict[str, IncomingProfileConfig] = Field(default_factory=dict)
  profile_overrides: Dict[str, IncomingProfileConfig] = Field(default_factory=dict)
  audio: IncomingCallAudioConfig = Field(default_factory=IncomingCallAudioConfig)
  voicemail: IncomingVoicemailConfig = Field(default_factory=IncomingVoicemailConfig)
  number_patterns: IncomingNumberPatternsConfig = Field(
      default_factory=IncomingNumberPatternsConfig
  )
  advanced: IncomingCallAdvancedConfig = Field(default_factory=IncomingCallAdvancedConfig)


class ResolvedProfileDecision(BaseModel):
  """Profil resolu avec valeurs effectives (apres merge preset + overrides)."""

  profile: IncomingProfileName
  rings_before_answer: int
  actions: List[IncomingAction]
  seize_on_ring: bool
  require_cid_before_action: bool
  source: str = "preset:voicemail"


class CallDecision(BaseModel):
  """Decision policy pour un appel entrant (logs + health daemon)."""

  profile: IncomingProfileName
  actions: List[IncomingAction]
  rings_before_answer: int
  seize_on_ring: bool
  require_cid_before_action: bool
  source: str
  should_ignore: bool = False
  should_answer: bool = False
