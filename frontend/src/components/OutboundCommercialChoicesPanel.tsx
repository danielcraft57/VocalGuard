/**
 * Panneau co-pilote commercial : top-5 situations puis 5 formulations (clavier 1-5).
 */

"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  chooseCommercialPhrase,
  fetchCommercialPhrases,
  fetchCommercialPresentation,
  getCommercialVoiceUrl,
  type CommercialPhrase,
  type CommercialSuggestion
} from "../services/outboundCommercialApi";

type Step = "intents" | "phrases" | "presentation";

export type CommercialPlaybackMode = "modem" | "speakers";

type Props = {
  open: boolean;
  callId: number | null;
  connected: boolean;
  suggestions: CommercialSuggestion[];
  onClearSuggestions?: () => void;
  /** modem = ligne telephonique ; speakers = HP du PC (simulateur). */
  playbackMode?: CommercialPlaybackMode;
  /** Message si aucune suggestion (defaut = attente STT). */
  emptyHint?: string;
};

const listBtn = (active: boolean): React.CSSProperties => ({
  display: "flex",
  gap: "10px",
  alignItems: "flex-start",
  width: "100%",
  textAlign: "left",
  padding: "10px 12px",
  marginBottom: "6px",
  borderRadius: "10px",
  border: active
    ? "1px solid rgba(56, 189, 248, 0.7)"
    : "1px solid rgba(71, 85, 105, 0.8)",
  background: active ? "rgba(14, 165, 233, 0.18)" : "rgba(15, 23, 42, 0.85)",
  color: "#e2e8f0",
  cursor: "pointer",
  fontSize: "0.8125rem",
  lineHeight: 1.4
});

/**
 * Affiche les choix commerciaux et reagit aux touches 1-5.
 *
 * @param props Suggestions WS + callId pour play.
 * @returns Panneau React.
 */
export function OutboundCommercialChoicesPanel({
  open,
  callId,
  connected,
  suggestions,
  onClearSuggestions,
  playbackMode = "modem",
  emptyHint
}: Props): React.ReactElement | null {
  const [step, setStep] = useState<Step>("intents");
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [phrases, setPhrases] = useState<CommercialPhrase[]>([]);
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [presentationLoaded, setPresentationLoaded] = useState(false);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (!open) {
      setStep("intents");
      setSelectedTag(null);
      setPhrases([]);
      setStatusMsg(null);
      setPresentationLoaded(false);
    }
  }, [open]);

  useEffect(() => {
    if (suggestions.length > 0) {
      setStep("intents");
      setSelectedTag(null);
      setPhrases([]);
      setStatusMsg(null);
    }
  }, [suggestions]);

  const loadPhrases = useCallback(async (tag: string) => {
    setBusy(true);
    setStatusMsg(null);
    try {
      const res = await fetchCommercialPhrases(tag);
      setSelectedTag(tag);
      setPhrases(res.phrases || []);
      setStep("phrases");
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : "Chargement phrases echoue");
    } finally {
      setBusy(false);
    }
  }, []);

  const playPhrase = useCallback(
    async (variantIndex: number) => {
      if (!selectedTag) return;
      setBusy(true);
      setStatusMsg(null);
      try {
        const playOnModem =
          playbackMode === "modem" && Boolean(callId) && connected;
        const res = await chooseCommercialPhrase(
          selectedTag,
          variantIndex,
          callId,
          playOnModem
        );

        if (playbackMode === "speakers") {
          if (!res.wav_basename) {
            setStatusMsg("Pas de basename WAV pour cette phrase");
          } else {
            try {
              if (!audioRef.current) audioRef.current = new Audio();
              const el = audioRef.current;
              el.pause();
              el.src = getCommercialVoiceUrl(res.wav_basename);
              await el.play();
              setStatusMsg(`HP : ${res.text.slice(0, 80)}…`);
            } catch (playErr) {
              setStatusMsg(
                playErr instanceof Error
                  ? playErr.message
                  : "Lecture HP impossible (WAV manquant ?)"
              );
            }
          }
        } else if (res.played) {
          setStatusMsg(`Joue : ${res.text.slice(0, 80)}…`);
        } else if (res.play_error) {
          setStatusMsg(res.play_error);
        } else {
          setStatusMsg(`Choix OK (pas de lecture ligne) : ${res.wav_basename}`);
        }
        onClearSuggestions?.();
        setStep("intents");
        setSelectedTag(null);
        setPhrases([]);
      } catch (e) {
        setStatusMsg(e instanceof Error ? e.message : "Lecture echouee");
      } finally {
        setBusy(false);
      }
    },
    [selectedTag, callId, connected, onClearSuggestions, playbackMode]
  );

  const loadPresentation = useCallback(async () => {
    setBusy(true);
    setStatusMsg(null);
    try {
      const res = await fetchCommercialPresentation();
      setSelectedTag(res.tag);
      setPhrases(res.phrases || []);
      setStep("presentation");
      setPresentationLoaded(true);
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : "Presentation indisponible");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;

    const onKey = (ev: KeyboardEvent) => {
      const target = ev.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      const digit = ev.key;
      if (!/^[1-5]$/.test(digit)) return;
      const idx = Number(digit) - 1;
      ev.preventDefault();
      if (step === "intents" && suggestions[idx]) {
        void loadPhrases(suggestions[idx].tag);
      } else if ((step === "phrases" || step === "presentation") && phrases[idx]) {
        void playPhrase(phrases[idx].variant_index);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, step, suggestions, phrases, loadPhrases, playPhrase]);

  if (!open) return null;

  const showIntents = step === "intents";
  const showPhrases = step === "phrases" || step === "presentation";

  return (
    <div
      style={{
        margin: "8px 12px 0",
        padding: "12px",
        borderRadius: "14px",
        background: "rgba(15, 23, 42, 0.92)",
        border: "1px solid rgba(56, 189, 248, 0.35)",
        flexShrink: 0
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "8px",
          gap: "8px"
        }}
      >
        <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#7dd3fc" }}>
          {showIntents
            ? "Situations (touches 1-5)"
            : step === "presentation"
              ? "Presentation (touches 1-5)"
              : "Phrases (touches 1-5)"}
        </div>
        <div style={{ display: "flex", gap: "6px" }}>
          {!presentationLoaded && showIntents ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void loadPresentation()}
              style={{
                fontSize: "0.7rem",
                padding: "4px 8px",
                borderRadius: "8px",
                border: "1px solid rgba(148,163,184,0.4)",
                background: "transparent",
                color: "#cbd5e1",
                cursor: "pointer"
              }}
            >
              Ouverture
            </button>
          ) : null}
          {showPhrases ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setStep("intents");
                setSelectedTag(null);
                setPhrases([]);
              }}
              style={{
                fontSize: "0.7rem",
                padding: "4px 8px",
                borderRadius: "8px",
                border: "1px solid rgba(148,163,184,0.4)",
                background: "transparent",
                color: "#cbd5e1",
                cursor: "pointer"
              }}
            >
              Retour
            </button>
          ) : null}
        </div>
      </div>

      {showIntents && suggestions.length === 0 ? (
        <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>
          {emptyHint ||
            "En attente de la parole du prospect (STT) pour proposer 5 situations…"}
        </div>
      ) : null}

      {showIntents
        ? suggestions.slice(0, 5).map((s) => (
            <button
              key={s.tag}
              type="button"
              disabled={busy}
              onClick={() => void loadPhrases(s.tag)}
              style={listBtn(false)}
            >
              <span
                style={{
                  flexShrink: 0,
                  width: "22px",
                  height: "22px",
                  borderRadius: "6px",
                  background: "rgba(56,189,248,0.25)",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: 700,
                  fontSize: "0.75rem"
                }}
              >
                {s.key}
              </span>
              <span style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, marginBottom: "2px" }}>
                  {s.tag.replace(/^out_/, "").replace(/_/g, " ")}
                  <span style={{ opacity: 0.6, fontWeight: 400, marginLeft: "6px" }}>
                    {Math.round((s.score || 0) * 100)}%
                    {s.wav_ready_any === false ? " · WAV manquant" : ""}
                  </span>
                </div>
                <div style={{ color: "#94a3b8" }}>{s.preview}</div>
              </span>
            </button>
          ))
        : null}

      {showPhrases
        ? phrases.slice(0, 5).map((p) => (
            <button
              key={`${selectedTag}-${p.variant_index}`}
              type="button"
              disabled={busy || !p.wav_ready}
              onClick={() => void playPhrase(p.variant_index)}
              style={listBtn(false)}
              title={p.wav_ready ? "Jouer sur la ligne" : "WAV manquant - regenerer les voix"}
            >
              <span
                style={{
                  flexShrink: 0,
                  width: "22px",
                  height: "22px",
                  borderRadius: "6px",
                  background: p.wav_ready
                    ? "rgba(34,197,94,0.3)"
                    : "rgba(239,68,68,0.25)",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: 700,
                  fontSize: "0.75rem"
                }}
              >
                {p.key}
              </span>
              <span style={{ flex: 1, color: p.wav_ready ? "#e2e8f0" : "#fca5a5" }}>
                {p.text}
              </span>
            </button>
          ))
        : null}

      {statusMsg ? (
        <div style={{ marginTop: "8px", fontSize: "0.7rem", color: "#fcd34d" }}>
          {statusMsg}
        </div>
      ) : null}
      {busy ? (
        <div style={{ marginTop: "6px", fontSize: "0.7rem", color: "#94a3b8" }}>…</div>
      ) : null}
    </div>
  );
}
