/**
 * Poll partage de l'etat telephonie (Topbar + bandeau dashboard).
 * Cache memoire/session + abort au unmount.
 */

"use client";

import { useEffect, useState } from "react";
import {
  fetchTelephonyStatus,
  type TelephonyStatus
} from "../services/settingsApi";
import {
  isAbortError,
  loadUiCache,
  saveUiCache,
  UI_CACHE_KEYS
} from "../services/uiPersist";

/**
 * Snapshot modem / daemon avec poll et cache.
 *
 * @param pollMs Intervalle (0 = une seule fois).
 * @returns Etat telephonie ou null.
 */
export function useTelephonyStatus(pollMs = 8000): TelephonyStatus | null {
  const [tel, setTel] = useState<TelephonyStatus | null>(null);

  useEffect(() => {
    const cached = loadUiCache<TelephonyStatus>(UI_CACHE_KEYS.telephonyStatus);
    if (cached) setTel(cached);

    let cancelled = false;
    let current: AbortController | null = null;

    const tick = () => {
      current?.abort();
      const ac = new AbortController();
      current = ac;
      fetchTelephonyStatus(ac.signal)
        .then((s) => {
          if (cancelled) return;
          setTel(s);
          saveUiCache(UI_CACHE_KEYS.telephonyStatus, s);
        })
        .catch((e) => {
          if (isAbortError(e) || cancelled) return;
          setTel((prev) =>
            prev ?? {
              status: "unreachable",
              modem_initialized: false,
              incoming_line_mode: "voicemail",
              in_call: false,
              relay_failures: 0,
              daemon_reachable: false
            }
          );
        });
    };

    tick();
    if (pollMs <= 0) {
      return () => {
        cancelled = true;
        current?.abort();
      };
    }
    const id = window.setInterval(tick, pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      current?.abort();
    };
  }, [pollMs]);

  return tel;
}
