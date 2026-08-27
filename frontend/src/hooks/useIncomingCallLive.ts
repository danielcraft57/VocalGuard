"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getWsBaseUrl } from "../services/httpClient";

export type IncomingLivePhase = "ringing" | "answered" | "blocked" | "ended";

export type IncomingLiveCall = {
  callId: number;
  phoneNumber: string | null;
  callerName: string | null;
  phase: IncomingLivePhase;
  startedAt: number;
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

/**
 * Abonne /ws/events pour une modale d'appel entrant globale.
 *
 * @returns Etat live + dismiss manuel (fermeture anticipee).
 */
export function useIncomingCallLive(): {
  live: IncomingLiveCall | null;
  dismiss: () => void;
} {
  const [live, setLive] = useState<IncomingLiveCall | null>(null);
  const closeTimer = useRef<number | null>(null);

  const clearCloseTimer = useCallback(() => {
    if (closeTimer.current != null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const dismiss = useCallback(() => {
    clearCloseTimer();
    setLive(null);
  }, [clearCloseTimer]);

  const scheduleAutoClose = useCallback(
    (delayMs: number) => {
      clearCloseTimer();
      closeTimer.current = window.setTimeout(() => {
        setLive(null);
        closeTimer.current = null;
      }, delayMs);
    },
    [clearCloseTimer]
  );

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
          clearCloseTimer();
          setLive({
            callId,
            phoneNumber: asOptStr(data.phone_number),
            callerName: asOptStr(data.caller_name),
            phase: "ringing",
            startedAt: Date.now()
          });
          return;
        }

        if (t === "call.updated") {
          setLive((prev) => {
            if (!prev || prev.callId !== callId) {
              // Event update sans incoming (course) : ouvrir quand meme la modale.
              return {
                callId,
                phoneNumber: asOptStr(data.phone_number),
                callerName: asOptStr(data.caller_name),
                phase: "answered",
                startedAt: Date.now()
              };
            }
            return {
              ...prev,
              phoneNumber: asOptStr(data.phone_number) ?? prev.phoneNumber,
              callerName: asOptStr(data.caller_name) ?? prev.callerName
            };
          });
          return;
        }

        if (t === "call.answered") {
          setLive((prev) => {
            if (prev && prev.callId === callId) {
              return { ...prev, phase: "answered" };
            }
            return {
              callId,
              phoneNumber: asOptStr(data.phone_number),
              callerName: asOptStr(data.caller_name),
              phase: "answered",
              startedAt: Date.now()
            };
          });
          return;
        }

        if (t === "call.blocked") {
          setLive((prev) => {
            if (prev && prev.callId !== callId) return prev;
            return {
              callId,
              phoneNumber: (prev && prev.callId === callId ? prev.phoneNumber : null) ?? asOptStr(data.phone_number),
              callerName: (prev && prev.callId === callId ? prev.callerName : null) ?? asOptStr(data.caller_name),
              phase: "blocked",
              startedAt: prev?.startedAt ?? Date.now()
            };
          });
          scheduleAutoClose(2200);
          return;
        }

        if (t === "call.completed" || t === "call.missed") {
          setLive((prev) => {
            if (!prev || prev.callId !== callId) return prev;
            return { ...prev, phase: "ended" };
          });
          scheduleAutoClose(1600);
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
  }, [clearCloseTimer, scheduleAutoClose]);

  return { live, dismiss };
}
