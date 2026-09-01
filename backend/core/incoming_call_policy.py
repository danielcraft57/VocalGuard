"""
Moteur de decision pour les appels entrants (profils + actions).

Squelette S1 : classification statique + resolution preset. Integration async
(block_service) prevue en S3.
"""

from __future__ import annotations

from typing import Optional

from backend.core.config import Config
from backend.core.incoming_call_settings import (
    apply_incoming_call_settings,
    load_incoming_call_settings,
    resolve_profile_decision,
)
from backend.core.incoming_call_types import (
    CallDecision,
    IncomingCallSettingsData,
    IncomingProfileName,
)


from backend.core.number_pattern_matcher import match_number_pattern_profile as match_rules_profile


def match_number_pattern_profile(
    caller_id: Optional[str],
    settings: IncomingCallSettingsData,
) -> Optional[IncomingProfileName]:
    """
    Applique les regles number_patterns si activees.

    @param caller_id Numero normalise ou masque (P/O).
    @param settings Configuration.
    @returns Profil force ou None.
    """
    np = settings.number_patterns
    return match_rules_profile(caller_id, list(np.rules or []), enabled=bool(np.enabled))


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
    apply_incoming_call_settings(self._config, self.settings)
    try:
      self._config.incoming_call_settings = self.settings  # type: ignore[attr-defined]
    except Exception:
      pass

  def resolve_sync(
      self,
      *,
      caller_id: Optional[str] = None,
      is_whitelisted: bool = False,
      is_blocked: bool = False,
  ) -> CallDecision:
    """
    Resout la decision pour un appel (sync, flags deja connus).

    @param caller_id Numero pour patterns.
    @param is_whitelisted Liste blanche.
    @param is_blocked Liste noire.
    @returns CallDecision.
    """
    pattern_profile = None
    if not is_whitelisted:
        pattern_profile = match_number_pattern_profile(caller_id, self.settings)
    if is_whitelisted:
      profile = "permitted"
    elif pattern_profile is not None:
      profile = pattern_profile
    else:
      profile = classify_profile_sync(
          is_whitelisted=False,
          is_blocked=is_blocked,
          screened_when_unknown=bool(self.settings.screened_when_unknown),
      )
    decision = build_call_decision(self.settings, profile)
    if (
        profile == "permitted"
        and is_whitelisted
        and self.settings.whitelist_ring_only
        and "ignore" in decision.actions
    ):
      decision = decision.model_copy(update={"should_ignore": True, "should_answer": False})
    return decision

  async def resolve_async(
      self,
      block_service,
      *,
      caller_id: Optional[str] = None,
      caller_name: Optional[str] = None,
  ) -> CallDecision:
    """
    Classifie via block_service puis resout la decision.

    @param block_service Service listes blanche/noire.
    @param caller_id Numero appelant.
    @param caller_name Nom CID.
    @returns CallDecision memorisee.
    """
    is_whitelisted = False
    is_blocked = False
    if caller_id:
      try:
        is_whitelisted = await block_service.is_whitelisted(caller_id)
      except Exception:
        pass
    if not is_whitelisted and caller_id:
      try:
        is_blocked = await block_service.is_blocked(caller_id, caller_name)
      except Exception:
        pass
    decision = self.resolve_sync(
        caller_id=caller_id,
        is_whitelisted=is_whitelisted,
        is_blocked=is_blocked,
    )
    self.remember_decision(decision)
    return decision

  def resolve_sync_legacy(
      self,
      *,
      is_whitelisted: bool = False,
      is_blocked: bool = False,
  ) -> CallDecision:
    """Alias tests S1 (sans caller_id)."""
    return self.resolve_sync(is_whitelisted=is_whitelisted, is_blocked=is_blocked)

  @property
  def last_decision_summary(self) -> Optional[str]:
    """Resume pour health (derniere decision si stockee)."""
    return getattr(self, "_last_summary", None)

  def remember_decision(self, decision: CallDecision) -> None:
    """Memorise la derniere decision (health UI)."""
    self._last_summary = (
        f"{decision.profile} | {decision.source} | "
        f"rings={decision.rings_before_answer} | "
        f"ignore={decision.should_ignore}"
    )
