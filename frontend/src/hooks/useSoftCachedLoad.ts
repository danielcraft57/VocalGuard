/**
 * Charge des donnees avec cache session + soft sync + abort au unmount.
 */

"use client";

import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import {
  isAbortError,
  isUiCacheFresh,
  loadUiCache,
  saveUiCache,
  UI_CACHE_TTL_MS
} from "../services/uiPersist";

export type SoftCachedLoadOptions<T> = {
  /** Cle session/memoire. */
  cacheKey: string;
  /** Fetcher reseau (recoit AbortSignal). */
  fetcher: (signal: AbortSignal) => Promise<T>;
  /** TTL avant soft refresh (defaut 2 min). */
  ttlMs?: number;
  /** True si le cache contient deja des donnees utilisables. */
  hasData?: (data: T | null) => boolean;
};

export type SoftCachedLoadResult<T> = {
  data: T | null;
  setData: Dispatch<SetStateAction<T | null>>;
  loading: boolean;
  syncing: boolean;
  error: string | null;
  setError: Dispatch<SetStateAction<string | null>>;
  reload: (opts?: { soft?: boolean; force?: boolean }) => Promise<void>;
};

/**
 * Hydrate depuis le cache puis soft-sync reseau ; abort si on quitte la page.
 *
 * @param options Cle + fetcher.
 * @returns Etat UI + reload.
 */
export function useSoftCachedLoad<T>(
  options: SoftCachedLoadOptions<T>
): SoftCachedLoadResult<T> {
  const { cacheKey, fetcher, ttlMs = UI_CACHE_TTL_MS } = options;
  const hasDataFn =
    options.hasData ?? ((d: T | null) => d !== null && d !== undefined);

  const cached = loadUiCache<T>(cacheKey);
  const [data, setData] = useState<T | null>(() => cached);
  const [loading, setLoading] = useState(() => !hasDataFn(cached));
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const reload = useCallback(
    async (opts?: { soft?: boolean; force?: boolean }) => {
      const current = loadUiCache<T>(cacheKey);
      const already = hasDataFn(current);
      const soft = Boolean(opts?.soft) || (already && !opts?.force);
      const skipNetwork =
        !opts?.force && already && isUiCacheFresh(cacheKey, ttlMs);

      if (skipNetwork) {
        setData(current);
        setLoading(false);
        setSyncing(false);
        return;
      }

      if (soft) setSyncing(true);
      else if (!already) setLoading(true);
      setError(null);

      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      try {
        const next = await fetcherRef.current(ac.signal);
        if (ac.signal.aborted) return;
        setData(next);
        saveUiCache(cacheKey, next);
      } catch (e) {
        if (isAbortError(e) || ac.signal.aborted) return;
        if (!already) {
          setError(e instanceof Error ? e.message : "Chargement impossible");
        }
      } finally {
        if (!ac.signal.aborted) {
          setLoading(false);
          setSyncing(false);
        }
      }
    },
    [cacheKey, ttlMs, hasDataFn]
  );

  useEffect(() => {
    void reload({ soft: hasDataFn(loadUiCache<T>(cacheKey)) });
    return () => {
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount once per key
  }, [cacheKey]);

  return { data, setData, loading, syncing, error, setError, reload };
}
