"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchIncomingCallConfig,
  patchIncomingCallConfig,
  type IncomingCallConfig,
  type IncomingCallConfigPatch
} from "../services/settingsApi";

const AUTOSAVE_DELAY_MS = 650;

/**
 * Hook pour charger et sauvegarder la config appels entrants (auto-save debounce).
 */
export function useIncomingCallConfig() {
  const [config, setConfig] = useState<IncomingCallConfig | null>(null);
  const [draft, setDraft] = useState<IncomingCallConfigPatch>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const draftRef = useRef(draft);
  const savingRef = useRef(false);
  const pendingAfterSaveRef = useRef(false);

  draftRef.current = draft;

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchIncomingCallConfig();
      setConfig(data);
      setDraft({});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chargement impossible");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

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
