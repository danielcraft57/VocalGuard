"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getWsBaseUrl, getApiBaseUrl } from "../services/httpClient";

export type IncomingLivePhase = "ringing" | "answered" | "blocked" | "ended";

export type IncomingBeliefRow = {
  tag: string;
  score: number;
};

export type IncomingLiveCall = {
  callId: number;
  phoneNumber: string | null;
  callerName: string | null;
  phase: IncomingLivePhase;
  /** Epoch ms : demarre au decrochage (pas a la sonnerie). */
  startedAt: number;
  /** Texte STT live (chunk en cours). */
  liveTranscript: string;
  /** Tours confirmes (live:false / commit). */
  confirmedTranscript: string;
  belief: IncomingBeliefRow[];
  committedTag: string | null;
};

type WsEnvelope = {
  type?: string;
  data?: Record<string, unknown>;
};

function asCallId(raw: unknown): number | null {
  const n = typeof raw === "number" ? raw : Number(raw);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function asOptStr(raw: unknown): string | null {
  if (raw == null) return null;
  const s = String(raw).trim();
  return s ? s : null;
}

function emptyConversationFields() {
  return {
    liveTranscript: "",
    confirmedTranscript: "",
    belief: [] as IncomingBeliefRow[],
    committedTag: null as string | null
  };
}

/**
 * Abonne /ws/events pour une modale d'appel entrant globale.
 *
 * Chrono = depuis call.answered. STT chunks / belief pendant la conversation.
 * Filet HTTP : si call.completed rate le WS, le poll ferme la popin.
 *
 * @returns Etat live + dismiss manuel (fermeture anticipee).
 */
export function useIncomingCallLive(): {
  live: IncomingLiveCall | null;
  dismiss: () => void;
} {
  const [live, setLive] = useState<IncomingLiveCall | null>(null);
  const closeTimer = useRef<number | null>(null);
  /** Apres Masquer / fin : ignore call.updated qui rouvrait la popin. */
  const dismissedIds = useRef<Set<number>>(new Set());

  const clearCloseTimer = useCallback(() => {
    if (closeTimer.current != null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const dismiss = useCallback(() => {
    clearCloseTimer();
    setLive((prev) => {
      if (prev) dismissedIds.current.add(prev.callId);
      return null;
    });
  }, [clearCloseTimer]);

  const scheduleAutoClose = useCallback(
    (delayMs: number) => {
      clearCloseTimer();
      closeTimer.current = window.setTimeout(() => {
        setLive((prev) => {
          if (prev) dismissedIds.current.add(prev.callId);
          return null;
        });
        closeTimer.current = null;
      }, delayMs);
    },
    [clearCloseTimer]
  );

  const markEnded = useCallback(
    (callId: number) => {
      if (dismissedIds.current.has(callId)) return;
      setLive((prev) => {
        if (!prev || prev.callId !== callId) return prev;
        if (prev.phase === "ended") return prev;
        return { ...prev, phase: "ended" };
      });
      scheduleAutoClose(400);
    },
    [scheduleAutoClose]
  );

  // Filet : poll statut appel si le WS rate call.completed.
  useEffect(() => {
    if (!live || (live.phase !== "answered" && live.phase !== "ringing")) {
      return undefined;
    }
    const callId = live.callId;
    let cancelled = false;

    const check = async () => {
      try {
        const res = await fetch(`${getApiBaseUrl()}/calls/${callId}`);
        if (!res.ok || cancelled) return;
        const row = (await res.json()) as {
          status?: string;
          end_time?: string | null;
        };
        const status = String(row.status || "").toLowerCase();
        if (
          row.end_time ||
          status === "completed" ||
          status === "missed" ||
          status === "failed" ||
          status === "ended"
        ) {
          markEnded(callId);
        }
      } catch {
        /* ignore reseau */
      }
    };

    void check();
    const id = window.setInterval(() => void check(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [live?.callId, live?.phase, markEnded]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let cancelled = false;
    let retryMs = 1200;

    const connect = () => {
      if (cancelled) return;
      const url = `${getWsBaseUrl()}/ws/events`;
      try {
        ws = new WebSocket(url);
      } catch {
        window.setTimeout(connect, retryMs);
        retryMs = Math.min(8000, retryMs + 800);
        return;
      }

      ws.onopen = () => {
        retryMs = 1200;
      };

      ws.onmessage = (ev) => {
        let msg: WsEnvelope;
        try {
          msg = JSON.parse(String(ev.data)) as WsEnvelope;
        } catch {
          return;
        }
        const t = String(msg.type || "");
        const data = msg.data || {};
        const callId = asCallId(data.call_id);
        if (!callId) return;

        if (t === "call.incoming") {
          dismissedIds.current.delete(callId);
          clearCloseTimer();
          setLive({
            callId,
            phoneNumber: asOptStr(data.phone_number),
            callerName: asOptStr(data.caller_name),
            phase: "ringing",
            startedAt: 0,
            ...emptyConversationFields()
          });
          return;
        }

        if (t === "call.updated") {
          if (dismissedIds.current.has(callId)) return;
          setLive((prev) => {
            if (!prev || prev.callId !== callId) return prev;
            return {
              ...prev,
              phoneNumber: asOptStr(data.phone_number) ?? prev.phoneNumber,
              callerName: asOptStr(data.caller_name) ?? prev.callerName
            };
          });
          return;
        }

        if (t === "call.answered") {
          if (dismissedIds.current.has(callId)) return;
          clearCloseTimer();
          setLive((prev) => {
            if (prev && prev.callId === callId) {
              return {
                ...prev,
                phase: "answered",
                // Ne reset pas le chrono si deja en ligne (evite decalage).
                startedAt: prev.startedAt > 0 ? prev.startedAt : Date.now(),
                phoneNumber: asOptStr(data.phone_number) ?? prev.phoneNumber,
                callerName: asOptStr(data.caller_name) ?? prev.callerName
              };
            }
            return {
              callId,
              phoneNumber: asOptStr(data.phone_number),
              callerName: asOptStr(data.caller_name),
              phase: "answered",
              startedAt: Date.now(),
              ...emptyConversationFields()
            };
          });
          return;
        }

        if (t === "call.blocked") {
          setLive((prev) => {
            if (prev && prev.callId !== callId) return prev;
            return {
              callId,
              phoneNumber:
                (prev && prev.callId === callId ? prev.phoneNumber : null) ??
                asOptStr(data.phone_number),
              callerName:
                (prev && prev.callId === callId ? prev.callerName : null) ??
                asOptStr(data.caller_name),
              phase: "blocked",
              startedAt: prev?.startedAt && prev.startedAt > 0 ? prev.startedAt : Date.now(),
              ...emptyConversationFields()
            };
          });
          scheduleAutoClose(1400);
          return;
        }

        if (t === "call.completed" || t === "call.missed") {
          markEnded(callId);
          return;
        }

        if (
          t === "call.transcription.partial" ||
          t === "call.intent.belief" ||
          t === "call.intent.commit"
        ) {
          setLive((prev) => {
            if (!prev || prev.callId !== callId) return prev;
            if (prev.phase === "ended") return prev;

            const next: IncomingLiveCall = {
              ...prev,
              phase: prev.phase === "ringing" ? "answered" : prev.phase,
              startedAt: prev.startedAt > 0 ? prev.startedAt : Date.now()
            };

            if (t === "call.transcription.partial") {
              const text = String(data.text || "").trim();
              if (!text) return next;
              if (data.live === true) {
                return { ...next, liveTranscript: text };
              }
              return {
                ...next,
                liveTranscript: "",
                confirmedTranscript: next.confirmedTranscript
                  ? `${next.confirmedTranscript} ${text}`
                  : text
              };
            }

            if (t === "call.intent.belief") {
              const top = Array.isArray(data.top) ? data.top : [];
              const belief = top
                .map((row) => {
                  const r = row as { tag?: string; score?: number };
                  return { tag: String(r.tag || ""), score: Number(r.score || 0) };
                })
                .filter((r) => r.tag);
              return { ...next, belief };
            }

            if (t === "call.intent.commit") {
              const tag = String(data.tag || "").trim();
              const text = String(data.text || "").trim();
              return {
                ...next,
                committedTag: tag || next.committedTag,
                liveTranscript: "",
                confirmedTranscript: next.confirmedTranscript || text
              };
            }

            return next;
          });
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        window.setTimeout(connect, retryMs);
        retryMs = Math.min(8000, retryMs + 800);
      };

      ws.onerror = () => {
        try {
          ws?.close();
        } catch {
          /* ignore */
        }
      };
    };

    connect();
    return () => {
      cancelled = true;
      clearCloseTimer();
      try {
        ws?.close();
      } catch {
        /* ignore */
      }
    };
  }, [clearCloseTimer, scheduleAutoClose, markEnded]);

  return { live, dismiss };
}
