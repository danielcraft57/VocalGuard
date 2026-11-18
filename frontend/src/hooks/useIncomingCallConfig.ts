"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchIncomingCallConfig,
  patchIncomingCallConfig,
  type IncomingCallConfig,
  type IncomingCallConfigPatch
} from "../services/settingsApi";
import {
  isAbortError,
  isUiCacheFresh,
  loadUiCache,
  saveUiCache,
  UI_CACHE_KEYS
} from "../services/uiPersist";

const AUTOSAVE_DELAY_MS = 650;

/**
 * Hook pour charger et sauvegarder la config appels entrants (auto-save debounce).
 * Cache session partage entre sous-pages settings + abort au unmount.
 */
export function useIncomingCallConfig() {
  const cached = loadUiCache<IncomingCallConfig>(UI_CACHE_KEYS.incomingCallConfig);
  const [config, setConfig] = useState<IncomingCallConfig | null>(() => cached);
  const [draft, setDraft] = useState<IncomingCallConfigPatch>({});
  const [loading, setLoading] = useState(() => !cached);
  const [syncing, setSyncing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const draftRef = useRef(draft);
  const savingRef = useRef(false);
  const pendingAfterSaveRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  draftRef.current = draft;

  const reload = useCallback(async (opts?: { soft?: boolean; force?: boolean }) => {
    const current = loadUiCache<IncomingCallConfig>(UI_CACHE_KEYS.incomingCallConfig);
    const already = Boolean(current);
    const soft = Boolean(opts?.soft) && already;
    if (
      !opts?.force &&
      already &&
      isUiCacheFresh(UI_CACHE_KEYS.incomingCallConfig)
    ) {
      setConfig(current);
      setLoading(false);
      return;
    }

    if (soft) setSyncing(true);
    else if (!already) setLoading(true);
    setError(null);

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    try {
      const data = await fetchIncomingCallConfig(ac.signal);
      if (ac.signal.aborted) return;
      setConfig(data);
      saveUiCache(UI_CACHE_KEYS.incomingCallConfig, data);
      setDraft({});
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
  }, []);

  useEffect(() => {
    void reload({ soft: Boolean(cached) });
    return () => {
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount
  }, []);

  const patchField = useCallback(<K extends keyof IncomingCallConfigPatch>(
    key: K,
    value: IncomingCallConfigPatch[K]
  ) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
    setSuccess(null);
  }, []);

  const effective = config
    ? ({ ...config, ...draft } as IncomingCallConfig)
    : null;

  const dirty = Object.keys(draft).length > 0;

  const save = useCallback(async (): Promise<boolean> => {
    const payload = { ...draftRef.current };
    if (Object.keys(payload).length === 0) return true;
    if (savingRef.current) {
      pendingAfterSaveRef.current = true;
      return false;
    }
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      const updated = await patchIncomingCallConfig(payload);
      setConfig(updated);
      saveUiCache(UI_CACHE_KEYS.incomingCallConfig, updated);
      setDraft((prev) => {
        const next: IncomingCallConfigPatch = { ...prev };
        for (const key of Object.keys(payload) as (keyof IncomingCallConfigPatch)[]) {
          if (JSON.stringify(next[key]) === JSON.stringify(payload[key])) {
            delete next[key];
          }
        }
        return next;
      });
      setSuccess("Enregistre automatiquement");
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Echec enregistrement");
      return false;
    } finally {
      savingRef.current = false;
      setSaving(false);
      if (pendingAfterSaveRef.current) {
        pendingAfterSaveRef.current = false;
        window.setTimeout(() => {
          void save();
        }, AUTOSAVE_DELAY_MS);
      }
    }
  }, []);

  useEffect(() => {
    if (!dirty || loading) return undefined;
    const timer = window.setTimeout(() => {
      void save();
    }, AUTOSAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [draft, dirty, loading, save]);

  return {
    config: effective,
    loading,
    syncing,
    saving,
    dirty,
    error,
    success,
    setError,
    setSuccess,
    patchField,
    save,
    reload,
    autoSave: true as const
  };
}
