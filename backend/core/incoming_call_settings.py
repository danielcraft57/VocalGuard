"""
Chargement, fusion et persistance de la configuration appels entrants.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from loguru import logger

from backend.core.config import Config
from backend.core.incoming_call_types import (
    IncomingCallPresetConfig,
    IncomingCallSettingsData,
    IncomingLineMode,
    IncomingProfileConfig,
    IncomingProfileName,
    ResolvedProfileDecision,
)
from backend.core.incoming_line_mode import resolve_incoming_line_mode


def _default_presets() -> Dict[str, IncomingCallPresetConfig]:
  """Presets par defaut repondeur / telephone."""
  return {
      "voicemail": IncomingCallPresetConfig(
          label="Repondeur",
          permitted_actions=["ignore"],
          screened_actions=["answer", "greeting", "record"],
          blocked_actions=["answer", "greeting", "hangup"],
          permitted_rings=0,
          screened_rings=0,
          blocked_rings=0,
      ),
      "phone": IncomingCallPresetConfig(
          label="Telephone",
          permitted_actions=["ignore"],
          screened_actions=["ignore"],
          blocked_actions=["ignore"],
          permitted_rings=4,
          screened_rings=4,
          blocked_rings=4,
      ),
  }


def settings_path(config: Config) -> Path:
  """
  Chemin du fichier runtime incoming_call_settings.yaml.

  @param config Configuration applicative.
  @returns Chemin absolu.
  """
  base = Path(config.base_path) if config.base_path else Path.cwd()
  return (base / "data" / "incoming_call_settings.yaml").resolve()


def default_settings_data() -> IncomingCallSettingsData:
  """
  Configuration par defaut (presets inclus).

  @returns Modele Pydantic initialise.
  """
  return IncomingCallSettingsData(presets=_default_presets())


def _deep_merge_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
  """Fusion recursive de dictionnaires (patch ecrase les feuilles)."""
  out = deepcopy(base)
  for key, value in patch.items():
    if isinstance(value, dict) and isinstance(out.get(key), dict):
      out[key] = _deep_merge_dict(out[key], value)
    else:
      out[key] = value
  return out


def load_incoming_call_settings(config: Config) -> IncomingCallSettingsData:
  """
  Charge la config appels entrants (fichier + sync champs Config).

  @param config Configuration live.
  @returns Settings merges.
  """
  data = default_settings_data()
  path = settings_path(config)
  if path.is_file():
    try:
      with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
      if isinstance(raw, dict):
        data = IncomingCallSettingsData.model_validate(
            _deep_merge_dict(data.model_dump(), raw)
        )
    except Exception as exc:
      logger.warning("Lecture incoming_call_settings {}: {}", path, exc)

  # Sync depuis Config runtime (priorite aux champs deja appliques par incoming_line_mode).
  data.cid_wait_sec = float(getattr(config, "cid_wait_sec", data.cid_wait_sec) or data.cid_wait_sec)
  data.instant_seize_cid_grace_sec = float(
      getattr(config, "instant_seize_cid_grace_sec", data.instant_seize_cid_grace_sec)
      or data.instant_seize_cid_grace_sec
  )
  data.phone_mode_rings = int(
      getattr(config, "phone_mode_rings", data.phone_mode_rings) or data.phone_mode_rings
  )
  data.whitelist_ring_only = bool(
      getattr(config, "whitelist_ring_only", data.whitelist_ring_only)
  )
  data.active_preset = resolve_incoming_line_mode(config)  # type: ignore[assignment]
  if not data.presets:
    data.presets = _default_presets()
  return data


def apply_incoming_call_settings(config: Config, settings: IncomingCallSettingsData) -> None:
  """
  Applique les champs plats sur l'objet Config en memoire.

  @param config Configuration a muter.
  @param settings Settings source.
  """
  config.cid_wait_sec = float(settings.cid_wait_sec)
  config.instant_seize_cid_grace_sec = float(settings.instant_seize_cid_grace_sec)
  config.phone_mode_rings = int(settings.phone_mode_rings)
  config.whitelist_ring_only = bool(settings.whitelist_ring_only)
  if settings.audio and settings.audio.edge_tts_rate:
    config.edge_tts_rate = str(settings.audio.edge_tts_rate)
  if hasattr(config, "incoming_call_settings"):
    config.incoming_call_settings = settings  # type: ignore[attr-defined]


def save_incoming_call_settings(config: Config, settings: IncomingCallSettingsData) -> None:
  """
  Persiste incoming_call_settings.yaml.

  @param config Configuration (base_path).
  @param settings Donnees a ecrire.
  """
  path = settings_path(config)
  path.parent.mkdir(parents=True, exist_ok=True)
  settings.active_preset = resolve_incoming_line_mode(config)  # type: ignore[assignment]
  payload = settings.model_dump(mode="json")
  with open(path, "w", encoding="utf-8") as f:
    yaml.safe_dump(payload, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
  logger.info("incoming_call_settings sauvegarde: {}", path)


def patch_incoming_call_settings(
    config: Config,
    patch: Dict[str, Any],
) -> IncomingCallSettingsData:
  """
  Merge un patch partiel, applique sur Config et persiste.

  @param config Configuration live.
  @param patch Champs partiels (merge profond).
  @returns Settings apres merge.
  """
  current = load_incoming_call_settings(config)
  merged = IncomingCallSettingsData.model_validate(
      _deep_merge_dict(current.model_dump(), patch)
  )
  apply_incoming_call_settings(config, merged)
  from backend.core.incoming_line_mode import apply_incoming_line_mode, resolve_incoming_line_mode

  mode = resolve_incoming_line_mode(config)
  apply_incoming_line_mode(config, mode)
  save_incoming_call_settings(config, merged)
  return merged


def resolve_active_preset(settings: IncomingCallSettingsData) -> IncomingCallPresetConfig:
  """
  Retourne le preset actif (voicemail ou phone).

  @param settings Configuration chargee.
  @returns Preset effectif.
  """
  name: IncomingLineMode = settings.active_preset or "voicemail"
  presets = settings.presets or _default_presets()
  preset = presets.get(name)
  if preset is None:
    return _default_presets()[name]
  return preset


def resolve_profile_decision(
    settings: IncomingCallSettingsData,
    profile: IncomingProfileName,
) -> ResolvedProfileDecision:
  """
  Fusionne preset actif + profil + overrides pour un profil donne.

  @param settings Configuration complete.
  @param profile Nom du profil.
  @returns Decision resolue avec source explicite.
  """
  preset = resolve_active_preset(settings)
  preset_name = settings.active_preset or "voicemail"
  base_profiles = settings.profiles or {}
  overrides = settings.profile_overrides or {}

  rings_map = {
      "permitted": preset.permitted_rings,
      "screened": preset.screened_rings,
      "blocked": preset.blocked_rings,
  }
  actions_map = {
      "permitted": list(preset.permitted_actions),
      "screened": list(preset.screened_actions),
      "blocked": list(preset.blocked_actions),
  }

  rings = int(rings_map.get(profile, 0))
  actions = list(actions_map.get(profile, ["ignore"]))
  seize_on_ring = False
  require_cid = True

  prof = base_profiles.get(profile)
  if prof:
    if prof.rings_before_answer is not None:
      rings = int(prof.rings_before_answer)
    if prof.actions is not None:
      actions = list(prof.actions)
    if prof.seize_on_ring is not None:
      seize_on_ring = bool(prof.seize_on_ring)
    if prof.require_cid_before_action is not None:
      require_cid = bool(prof.require_cid_before_action)

  over = overrides.get(profile)
  if over:
    if over.rings_before_answer is not None:
      rings = int(over.rings_before_answer)
    if over.actions is not None:
      actions = list(over.actions)
    if over.seize_on_ring is not None:
      seize_on_ring = bool(over.seize_on_ring)
    if over.require_cid_before_action is not None:
      require_cid = bool(over.require_cid_before_action)

  if "answer" in actions and rings <= 0:
    if prof is None or prof.seize_on_ring is None:
      if over is None or over.seize_on_ring is None:
        seize_on_ring = True
  if profile == "blocked" and (prof is None or prof.require_cid_before_action is None):
    if over is None or over.require_cid_before_action is None:
      require_cid = False

  source = f"preset:{preset_name}"
  if over and over.model_dump(exclude_none=True):
    source = f"override:{profile}"
  elif prof and prof.model_dump(exclude_none=True):
    source = f"profile:{profile}"

  return ResolvedProfileDecision(
      profile=profile,
      rings_before_answer=rings,
      actions=actions,
      seize_on_ring=seize_on_ring,
      require_cid_before_action=require_cid,
      source=source,
  )
