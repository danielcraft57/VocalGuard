"""
Moteur de decision pour les appels entrants (profils + actions).

Squelette S1 : classification statique + resolution preset. Integration async
(block_service) prevue en S3.
"""

from __future__ import annotations

from typing import Optional

from backend.core.config import Config
from backend.core.incoming_call_settings import (
    load_incoming_call_settings,
    resolve_profile_decision,
)
from backend.core.incoming_call_types import (
    CallDecision,
    IncomingCallSettingsData,
    IncomingProfileName,
)


def classify_profile_sync(
    *,
    is_whitelisted: bool = False,
    is_blocked: bool = False,
    screened_when_unknown: bool = True,
) -> IncomingProfileName:
  """
  Classifie un appelant en profil permitted / screened / blocked.

  @param is_whitelisted Numero en liste blanche.
  @param is_blocked Numero bloque.
  @param screened_when_unknown Si True, inconnu -> screened.
  @returns Nom du profil.
  """
  if is_whitelisted:
    return "permitted"
  if is_blocked:
    return "blocked"
  if screened_when_unknown:
    return "screened"
  return "permitted"


def build_call_decision(
    settings: IncomingCallSettingsData,
    profile: IncomingProfileName,
) -> CallDecision:
  """
  Construit une CallDecision a partir du profil resolu.

  @param settings Configuration effective.
  @param profile Profil appelant.
  @returns Decision complete pour logs et runtime.
  """
  resolved = resolve_profile_decision(settings, profile)
  should_ignore = resolved.actions == ["ignore"] or (
      len(resolved.actions) == 1 and resolved.actions[0] == "ignore"
  )
  should_answer = "answer" in resolved.actions and not should_ignore
  return CallDecision(
      profile=profile,
      actions=list(resolved.actions),
      rings_before_answer=int(resolved.rings_before_answer),
      seize_on_ring=bool(resolved.seize_on_ring),
      require_cid_before_action=bool(resolved.require_cid_before_action),
      source=resolved.source,
      should_ignore=should_ignore,
      should_answer=should_answer,
  )


class IncomingCallPolicy:
  """
  Policy runtime attachee au CallManager.

  Charge les settings depuis Config et expose resolve() synchrone (S1).
  """

  def __init__(self, config: Config) -> None:
    self._config = config
    self.reload()

  def reload(self) -> None:
    """Recharge la configuration depuis disque + Config."""
    self.settings = load_incoming_call_settings(self._config)
    apply_on_config = getattr(self._config, "incoming_call_settings", None)
    if apply_on_config is None:
      try:
        self._config.incoming_call_settings = self.settings  # type: ignore[attr-defined]
      except Exception:
        pass

  def resolve_sync(
      self,
      *,
      is_whitelisted: bool = False,
      is_blocked: bool = False,
  ) -> CallDecision:
    """
    Resout la decision pour un appel (version synchrone, sans DB).

    @param is_whitelisted Liste blanche.
    @param is_blocked Liste noire.
    @returns CallDecision.
    """
    profile = classify_profile_sync(
        is_whitelisted=is_whitelisted,
        is_blocked=is_blocked,
        screened_when_unknown=bool(self.settings.screened_when_unknown),
    )
    return build_call_decision(self.settings, profile)

  @property
  def last_decision_summary(self) -> Optional[str]:
    """Resume pour health (derniere decision si stockee)."""
    return getattr(self, "_last_summary", None)

  def remember_decision(self, decision: CallDecision) -> None:
    """Memorise la derniere decision (health UI)."""
    self._last_summary = (
        f"{decision.profile}:{decision.source}:"
        f"rings={decision.rings_before_answer}:"
        f"ignore={decision.should_ignore}"
    )
