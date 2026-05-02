"use client";

import React from "react";
import { useOutgoingCallConnectChime, useOutgoingCallRingtone } from "../hooks/useOutgoingCallRingtone";
import { playDialerKeySound, playHangupSound, playOutgoingDialSound } from "../utils/telephonySounds";

export type OutgoingDialerStatus = "idle" | "dialing" | "connected" | "ended" | "error";

const KEYPAD = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"] as const;

const surface = {
  width: "min(400px, 100%)" as const,
  maxHeight: "92vh" as const,
  overflowX: "hidden" as const,
  overflowY: "auto" as const,
  display: "flex" as const,
  flexDirection: "column" as const,
  minHeight: 0 as const,
  borderRadius: "24px",
  background: "linear-gradient(180deg, #1e293b 0%, #0f172a 100%)",
  border: "1px solid rgba(148, 163, 184, 0.35)",
  boxShadow:
    "0 1px 2px rgba(0,0,0,0.35), 0 8px 24px rgba(0,0,0,0.45), 0 24px 48px rgba(0,0,0,0.35)"
};

const keyBase: React.CSSProperties = {
  aspectRatio: "1",
  minHeight: "48px",
  maxHeight: "56px",
  borderRadius: "50%",
  border: "none",
  fontSize: "1.125rem",
  fontWeight: 600,
  fontVariantNumeric: "tabular-nums",
  cursor: "pointer",
  transition: "transform 0.12s ease, box-shadow 0.12s ease, background 0.12s ease",
  boxShadow: "0 1px 2px rgba(0,0,0,0.45), 0 2px 4px rgba(0,0,0,0.25)"
};

type Props = {
  open: boolean;
  onClose: () => void;
  dialerNumber: string;
  setDialerNumber: (v: string) => void;
  dialerStatus: OutgoingDialerStatus;
  dialerCallId: number | null;
  dialerError: string | null;
  dialerLoading: boolean;
  liveListen: boolean;
  setLiveListen: (v: boolean) => void;
  liveMic: boolean;
  setLiveMic: (v: boolean) => void;
  audioActive: boolean;
  dialerLogs: { t: string; level: string; message: string }[];
  dialerLogsEndRef: React.RefObject<HTMLDivElement | null>;
  dialerTranscriptConfirmed: string;
  dialerTranscriptLive: string;
  canSendDtmf: boolean;
  onStartDial: () => void;
  onHangup: () => void;
  /** Touches pavé : composition (idle) ou DTMF (ligne). */
  onKeypadDigit: (digit: string) => void;
};

function TranscriptBox(props: {
  confirmed: string;
  live: string;
  minHeight: number;
  maxHeight: number | string;
  flex?: string;
}) {
  const { confirmed, live, minHeight, maxHeight, flex: flexVal } = props;
  return (
    <div
      style={{
        minHeight,
        maxHeight,
        ...(flexVal ? { flex: flexVal, minHeight: 0 } : {}),
        overflowY: "auto",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        background: "#020617",
        border: "1px solid rgba(71, 85, 105, 0.9)",
        borderRadius: "12px",
        padding: "12px 14px",
        fontSize: "0.9375rem",
        lineHeight: 1.5,
        color: "#f8fafc"
      }}
    >
      {!confirmed && !live ? (
        <span style={{ color: "#64748b", fontSize: "0.875rem" }}>En attente de parole…</span>
      ) : (
        <>
          {confirmed ? <span>{confirmed}</span> : null}
          {live ? (
            <span
              style={{
                color: "#fcd34d",
                fontStyle: "italic",
                fontWeight: 500,
                marginLeft: confirmed ? "0.35rem" : 0
              }}
            >
              {live}
            </span>
          ) : null}
        </>
      )}
    </div>
  );
}

export function OutgoingCallDialerModal(props: Props): React.ReactElement | null {
  const {
    open,
    onClose,
    dialerNumber,
    setDialerNumber,
    dialerStatus,
    dialerCallId,
    dialerError,
    dialerLoading,
    liveListen,
    setLiveListen,
    liveMic,
    setLiveMic,
    audioActive,
    dialerLogs,
    dialerLogsEndRef,
    dialerTranscriptConfirmed,
    dialerTranscriptLive,
    canSendDtmf,
    onStartDial,
    onHangup,
    onKeypadDigit
  } = props;

  const [callFeedOpen, setCallFeedOpen] = React.useState(true);

  useOutgoingCallRingtone(dialerStatus);
  useOutgoingCallConnectChime(dialerStatus);

  React.useEffect(() => {
    if (open) setCallFeedOpen(true);
  }, [open]);

  React.useEffect(() => {
    if (dialerStatus === "dialing") setCallFeedOpen(true);
  }, [dialerStatus]);

  if (!open) return null;

  const numberDisabled = dialerStatus === "dialing" || dialerStatus === "connected";
  const inCall = dialerStatus === "dialing" || dialerStatus === "connected";
  const showEndedFeed = dialerStatus === "ended" || dialerStatus === "error";

  /** Hors ligne : n’afficher le bloc journal/transcription qu’après fin d’appel/erreur ou s’il y a déjà du contenu (pas à l’ouverture « Prêt » vide). */
  const hasModemOrTranscript =
    dialerLogs.length > 0 ||
    dialerTranscriptConfirmed.trim().length > 0 ||
    dialerTranscriptLive.trim().length > 0;
  const showCompactCallFeed = !inCall && (showEndedFeed || (dialerStatus === "idle" && hasModemOrTranscript));

  const keypadEnabled =
    !dialerLoading &&
    (canSendDtmf || dialerStatus === "idle" || dialerStatus === "ended" || dialerStatus === "error");

  const showKeypad = !inCall || (inCall && !callFeedOpen);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: "1rem"
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Telephone sortant"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          ...surface,
          ...(inCall && callFeedOpen
            ? {
                height: "min(600px, 92vh)"
              }
            : {})
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            padding: "14px 18px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
            borderBottom: "1px solid rgba(51, 65, 85, 0.9)",
            flexShrink: 0
          }}
        >
          <span
            style={{
              fontSize: "0.75rem",
              color: "#e2e8f0",
              letterSpacing: "0.12em",
              fontWeight: 700,
              textTransform: "uppercase"
            }}
          >
            Appel sortant
          </span>
          <button
            type="button"
            onClick={() => {
              if (dialerCallId != null) playHangupSound();
              onClose();
            }}
            style={{
              border: "none",
              background: "rgba(71,85,105,0.65)",
              color: "#f1f5f9",
              cursor: "pointer",
              width: "40px",
              height: "40px",
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 1px 3px rgba(0,0,0,0.35)"
            }}
            aria-label="Fermer et raccrocher"
            title="Fermer et raccrocher"
          >
            <span className="material-icons" style={{ fontSize: "22px" }}>
              close
            </span>
          </button>
        </div>

        {inCall ? (
          <div
            style={{
              padding: "12px 16px 10px",
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              gap: "12px",
              borderBottom: "1px solid rgba(51,65,85,0.45)"
            }}
          >
            <div style={{ flex: 1, minWidth: 0, textAlign: "left" }}>
              <div
                style={{
                  fontSize: "1.125rem",
                  fontWeight: 600,
                  letterSpacing: "0.06em",
                  color: "#f8fafc",
                  fontVariantNumeric: "tabular-nums",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap"
                }}
              >
                {dialerNumber.trim() ? dialerNumber : "—"}
              </div>
              <div
                style={{
                  marginTop: "6px",
                  fontSize: "0.75rem",
                  color: "#94a3b8",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  flexWrap: "wrap"
                }}
              >
                {dialerStatus === "connected" && (
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "4px",
                      padding: "2px 8px",
                      borderRadius: "999px",
                      background: "rgba(34,197,94,0.15)",
                      color: "#4ade80",
                      fontWeight: 600
                    }}
                  >
                    <span className="material-icons" style={{ fontSize: "13px" }}>
                      call
                    </span>
                    En ligne
                  </span>
                )}
                {dialerStatus === "dialing" && (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                    <span className="material-icons vg-dialer-pulse" style={{ fontSize: "15px" }}>
                      graphic_eq
                    </span>
                    Composition…
                  </span>
                )}
                {dialerCallId != null && <span style={{ opacity: 0.75 }}>#{dialerCallId}</span>}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setCallFeedOpen((v) => !v)}
              title={callFeedOpen ? "Clavier (DTMF)" : "Journal & transcription"}
              aria-label={callFeedOpen ? "Afficher le clavier" : "Afficher journal et transcription"}
              style={{
                flexShrink: 0,
                width: "44px",
                height: "44px",
                borderRadius: "50%",
                border: "1px solid rgba(148,163,184,0.35)",
                background: "rgba(51,65,85,0.55)",
                color: "#e2e8f0",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "0 1px 3px rgba(0,0,0,0.25)"
              }}
            >
              <span className="material-icons" style={{ fontSize: "22px" }}>
                {callFeedOpen ? "dialpad" : "subject"}
              </span>
            </button>
          </div>
        ) : (
          <div style={{ padding: "16px 20px 8px", textAlign: "center", flexShrink: 0 }}>
            <div
              style={{
                fontSize: "1.875rem",
                fontWeight: 500,
                letterSpacing: "0.08em",
                color: "#f8fafc",
                fontVariantNumeric: "tabular-nums",
                lineHeight: 1.2
              }}
            >
              {dialerNumber.trim() ? dialerNumber : "—"}
            </div>
            <div
              style={{
                marginTop: "10px",
                fontSize: "0.8125rem",
                color: "#94a3b8",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px",
                flexWrap: "wrap"
              }}
            >
              {dialerStatus === "idle" && <span>Prêt</span>}
              {dialerStatus === "ended" && <span>Terminé</span>}
              {dialerStatus === "error" && <span style={{ color: "#f87171" }}>Erreur</span>}
              {dialerCallId != null && <span style={{ opacity: 0.75 }}>#{dialerCallId}</span>}
            </div>
          </div>
        )}

        <div
          style={{
            padding: "6px 20px 10px",
            display: "flex",
            gap: "1rem",
            justifyContent: "center",
            flexWrap: "wrap",
            flexShrink: 0
          }}
        >
          <label
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              fontSize: "0.8125rem",
              color: "#cbd5e1",
              cursor: audioActive ? "pointer" : "not-allowed",
              opacity: audioActive ? 1 : 0.45,
              userSelect: "none"
            }}
          >
            <input
              type="checkbox"
              checked={liveListen}
              disabled={!audioActive}
              onChange={(e) => setLiveListen(e.target.checked)}
              style={{ width: "18px", height: "18px", accentColor: "#38bdf8" }}
            />
            Écoute live
          </label>
          <label
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              fontSize: "0.8125rem",
              color: "#cbd5e1",
              cursor: audioActive ? "pointer" : "not-allowed",
              opacity: audioActive ? 1 : 0.45,
              userSelect: "none"
            }}
          >
            <input
              type="checkbox"
              checked={liveMic}
              disabled={!audioActive}
              onChange={(e) => setLiveMic(e.target.checked)}
              style={{ width: "18px", height: "18px", accentColor: "#38bdf8" }}
            />
            Micro PC
          </label>
        </div>

        {dialerError && (
          <div style={{ margin: "0 20px 8px", fontSize: "0.8125rem", color: "#fca5a5", lineHeight: 1.4 }}>{dialerError}</div>
        )}

        {inCall && callFeedOpen ? (
          <div
            style={{
              flex: 1,
              minHeight: 0,
              display: "flex",
              flexDirection: "column",
              gap: "10px",
              padding: "8px 20px 12px",
              overflow: "hidden",
              borderTop: "1px solid rgba(51,65,85,0.35)"
            }}
          >
            <div style={{ fontSize: "0.75rem", color: "#94a3b8", fontWeight: 600, flexShrink: 0 }}>Journal modem</div>
            <div
              style={{
                flex: "1 1 44%",
                minHeight: 0,
                overflowY: "auto",
                overflowX: "hidden",
                WebkitOverflowScrolling: "touch",
                background: "#020617",
                borderRadius: "12px",
                border: "1px solid #334155",
                padding: "10px 12px",
                fontFamily: "ui-monospace, monospace",
                fontSize: "0.75rem",
                lineHeight: 1.45,
                color: "#cbd5e1"
              }}
            >
              {dialerLogs.length === 0 ? (
                <span style={{ opacity: 0.65 }}>Aucun événement pour l’instant.</span>
              ) : (
                dialerLogs.map((l, i) => (
                  <div key={`${l.t}-${i}`} style={{ color: l.level === "error" ? "#fca5a5" : "#cbd5e1" }}>
                    <span style={{ opacity: 0.55 }}>[{l.t}]</span> {l.message}
                  </div>
                ))
              )}
              <div ref={dialerLogsEndRef} />
            </div>
            <div style={{ fontSize: "0.75rem", color: "#94a3b8", fontWeight: 600, flexShrink: 0 }}>Transcription</div>
            <TranscriptBox
              confirmed={dialerTranscriptConfirmed}
              live={dialerTranscriptLive}
              minHeight={48}
              maxHeight="none"
              flex="1 1 56%"
            />
          </div>
        ) : showCompactCallFeed ? (
          <div
            style={{
              padding: "4px 20px 8px",
              flexShrink: 0,
              minHeight: showEndedFeed ? "min(152px, 22vh)" : "min(168px, 24vh)",
              maxHeight: showEndedFeed ? "min(220px, 30vh)" : "min(240px, 32vh)",
              overflowY: "auto",
              overflowX: "hidden",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
              WebkitOverflowScrolling: "touch"
            }}
          >
            <details style={{ fontSize: "0.75rem", color: "#94a3b8", flexShrink: 0 }}>
              <summary style={{ cursor: "pointer", userSelect: "none", color: "#cbd5e1", fontWeight: 500 }}>Journal modem</summary>
              <div
                style={{
                  marginTop: "8px",
                  maxHeight: showEndedFeed ? "56px" : "72px",
                  overflowY: "auto",
                  background: "#020617",
                  borderRadius: "12px",
                  border: "1px solid #334155",
                  padding: "8px 10px",
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "0.72rem",
                  lineHeight: 1.45,
                  color: "#cbd5e1"
                }}
              >
                {dialerLogs.length === 0 ? (
                  <span style={{ opacity: 0.65 }}>Aucun événement pour l’instant.</span>
                ) : (
                  dialerLogs.map((l, i) => (
                    <div key={`${l.t}-${i}`} style={{ color: l.level === "error" ? "#fca5a5" : "#cbd5e1" }}>
                      <span style={{ opacity: 0.55 }}>[{l.t}]</span> {l.message}
                    </div>
                  ))
                )}
                <div ref={dialerLogsEndRef} />
              </div>
            </details>

            <div style={{ fontSize: "0.75rem", color: "#94a3b8", fontWeight: 600, marginTop: "2px", flexShrink: 0 }}>
              Transcription
            </div>
            <TranscriptBox
              confirmed={dialerTranscriptConfirmed}
              live={dialerTranscriptLive}
              minHeight={showEndedFeed ? 56 : 72}
              maxHeight={showEndedFeed ? 96 : 120}
            />
          </div>
        ) : null}

        {showKeypad && (
        <div
          style={{
            padding: "12px 20px 16px",
            display: "flex",
            justifyContent: "center",
            flexShrink: 0,
            position: "relative",
            zIndex: 2,
            isolation: "isolate",
            background: "linear-gradient(180deg, rgba(15,23,42,0.2) 0%, #0f172a 35%)"
          }}
        >
          <div
            style={{
              width: "100%",
              maxWidth: "280px",
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "12px",
              justifyItems: "center",
              touchAction: "manipulation"
            }}
          >
            {KEYPAD.map((digit) => (
              <button
                key={digit}
                type="button"
                disabled={!keypadEnabled}
                onClick={(ev) => {
                  ev.preventDefault();
                  ev.stopPropagation();
                  if (!keypadEnabled) return;
                  playDialerKeySound(digit);
                  onKeypadDigit(digit);
                }}
                style={{
                  ...keyBase,
                  width: "100%",
                  maxWidth: "72px",
                  background: keypadEnabled
                    ? "linear-gradient(180deg, #475569 0%, #334155 100%)"
                    : "#1e293b",
                  color: "#f1f5f9",
                  cursor: keypadEnabled ? "pointer" : "not-allowed",
                  opacity: keypadEnabled ? 1 : 0.45,
                  WebkitTapHighlightColor: "transparent"
                }}
                onMouseDown={(e) => {
                  if (keypadEnabled) (e.currentTarget as HTMLButtonElement).style.transform = "scale(0.94)";
                }}
                onMouseUp={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.transform = "";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.transform = "";
                }}
              >
                {digit}
              </button>
            ))}
          </div>
        </div>
        )}

        {/* Barre d’action : champ pleine largeur puis FAB alignés (Material) */}
        <div
          style={{
            padding: "12px 20px 20px",
            borderTop: "1px solid rgba(51, 65, 85, 0.9)",
            display: "flex",
            flexDirection: "column",
            gap: "14px",
            background: "rgba(15, 23, 42, 0.65)",
            flexShrink: 0
          }}
        >
          {!numberDisabled && (
            <input
              value={dialerNumber}
              onChange={(e) => setDialerNumber(e.target.value)}
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                e.preventDefault();
                if (dialerLoading || dialerStatus === "dialing" || dialerStatus === "connected") return;
                if (!dialerNumber.trim()) return;
                playOutgoingDialSound();
                onStartDial();
              }}
              placeholder="Numéro"
              className="vg-input"
              disabled={numberDisabled}
              inputMode="tel"
              autoComplete="tel"
              style={{
                width: "100%",
                borderRadius: "12px",
                fontSize: "1rem",
                padding: "12px 14px",
                border: "1px solid rgba(71, 85, 105, 0.95)",
                background: "rgba(2, 6, 23, 0.55)",
                color: "#f8fafc"
              }}
            />
          )}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "28px" }}>
            <button
              type="button"
              onClick={() => {
                playOutgoingDialSound();
                onStartDial();
              }}
              disabled={dialerLoading || dialerStatus === "dialing" || dialerStatus === "connected"}
              title="Appeler"
              aria-label="Appeler"
              style={{
                width: "64px",
                height: "64px",
                borderRadius: "50%",
                border: "none",
                background: "linear-gradient(180deg, #22c55e 0%, #15803d 100%)",
                color: "#fff",
                cursor: dialerLoading || dialerStatus === "dialing" || dialerStatus === "connected" ? "not-allowed" : "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "0 4px 12px rgba(34,197,94,0.45), 0 2px 4px rgba(0,0,0,0.35)",
                opacity: dialerLoading || dialerStatus === "dialing" || dialerStatus === "connected" ? 0.45 : 1,
                transition: "transform 0.1s ease"
              }}
            >
              <span className="material-icons" style={{ fontSize: "30px" }}>
                call
              </span>
            </button>
            <button
              type="button"
              onClick={() => {
                playHangupSound();
                onHangup();
              }}
              disabled={dialerCallId === null || dialerLoading}
              title="Raccrocher"
              aria-label="Raccrocher"
              style={{
                width: "64px",
                height: "64px",
                borderRadius: "50%",
                border: "none",
                background: "linear-gradient(180deg, #ef4444 0%, #b91c1c 100%)",
                color: "#fff",
                cursor: dialerCallId === null || dialerLoading ? "not-allowed" : "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "0 4px 12px rgba(239,68,68,0.45), 0 2px 4px rgba(0,0,0,0.35)",
                opacity: dialerCallId === null || dialerLoading ? 0.45 : 1
              }}
            >
              <span className="material-icons" style={{ fontSize: "30px" }}>
                call_end
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
