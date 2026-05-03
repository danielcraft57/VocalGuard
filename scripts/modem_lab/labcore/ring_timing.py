#!/usr/bin/env python3
"""Temps d'attente liés aux cycles de sonnerie (composition sortante, budgets lab)."""


def ringback_wait_sec(wait_rings: int, ring_duration_sec: float) -> float:
    """
    Durée d'attente **approximative** pour simuler N cycles sonnerie / silence.

    Équivalent à ``compute_ringback_wait_sec`` dans ``labscenarios/outbound_announce`` :
    on peut progressivement y migrer l'import pour un seul point de vérité.
    """
    n = max(0, int(wait_rings))
    period = max(0.0, float(ring_duration_sec))
    return float(n * period)
