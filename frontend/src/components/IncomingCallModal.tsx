"use client";

import React, { useEffect, useMemo } from "react";
import type { IncomingLiveCall } from "../hooks/useIncomingCallLive";
import { playIncomingAlertSound } from "../utils/telephonySounds";

type Props = {
  live: IncomingLiveCall | null;
  onDismiss: () => void;
};

function phaseLabel(phase: IncomingLiveCall["phase"]): string {
  switch (phase) {
    case "ringing":
      return "Appel entrant";
    case "answered":
      return "En ligne";
    case "blocked":
      return "Appel bloqué";
    case "ended":
      return "Fin d'appel";
    default:
      return "Appel";
  }
}

/**
 * Modale plein ecran pour un appel entrant (ouvre / ferme via evenements WS).
 */
export function IncomingCallModal({ live, onDismiss }: Props): React.ReactElement | null {
  const open = Boolean(live);
  const displayNumber = useMemo(() => {
    if (!live) return "Inconnu";
    return live.phoneNumber || live.callerName || "Inconnu";
  }, [live]);

  useEffect(() => {
    if (!live || live.phase !== "ringing") return;
    playIncomingAlertSound();
    const id = window.setInterval(() => playIncomingAlertSound(), 2200);
    return () => window.clearInterval(id);
  }, [live?.callId, live?.phase]);

  if (!open || !live) return null;

  const phase = live.phase;
  const isActive = phase === "ringing" || phase === "answered";

  return (
    <div
      className="vg-incoming-backdrop"
      role="presentation"
      onClick={() => {
        if (!isActive) onDismiss();
      }}
    >
      <div
        className={`vg-incoming-modal vg-incoming-modal--${phase}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="vg-incoming-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={`vg-incoming-pulse ${isActive ? "vg-incoming-pulse--on" : ""}`} aria-hidden>
          <span className="material-icons vg-incoming-icon">
            {phase === "blocked" ? "block" : phase === "ended" ? "call_end" : "ring_volume"}
          </span>
        </div>

        <p className="vg-incoming-eyebrow" id="vg-incoming-title">
          {phaseLabel(phase)}
        </p>
        <h2 className="vg-incoming-number">{displayNumber}</h2>
        {live.callerName && live.phoneNumber ? (
          <p className="vg-incoming-name">{live.callerName}</p>
        ) : (
          <p className="vg-incoming-name vg-incoming-name--muted">
            {phase === "answered"
              ? "Répondeur VocalGuard"
              : phase === "ringing"
                ? "Identification en cours…"
                : "\u00a0"}
          </p>
        )}

        <p className="vg-incoming-meta">Appel #{live.callId}</p>

        {!isActive ? (
          <button type="button" className="vg-incoming-dismiss" onClick={onDismiss}>
            Fermer
          </button>
        ) : (
          <p className="vg-incoming-hint">
            {phase === "ringing"
              ? "Décrochage automatique…"
              : "Se ferme à la fin de l'appel"}
          </p>
        )}
      </div>
    </div>
  );
}
