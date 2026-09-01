"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchIncomingCallConfig,
  patchIncomingCallConfig,
  type IncomingCallConfig,
  type IncomingCallConfigPatch
} from "../services/settingsApi";

/**
 * Hook pour charger et sauvegarder la config appels entrants.
 */
export function useIncomingCallConfig() {
  const [config, setConfig] = useState<IncomingCallConfig | null>(null);
  const [draft, setDraft] = useState<IncomingCallConfigPatch>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

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
  }, []);

  const effective = config
    ? ({ ...config, ...draft } as IncomingCallConfig)
    : null;

  const dirty = Object.keys(draft).length > 0;

  const save = useCallback(async (): Promise<boolean> => {
    if (!dirty) return true;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await patchIncomingCallConfig(draft);
      setConfig(updated);
      setDraft({});
      setSuccess("Parametres enregistres");
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Echec enregistrement");
      return false;
    } finally {
      setSaving(false);
    }
  }, [dirty, draft]);

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
    reload
  };
}
