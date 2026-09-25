"use client";

import React, { useEffect, useState } from "react";
import { Alert, CircularProgress, Typography } from "@mui/material";
import {
  fetchKbConversationStatus,
  isAbortError,
  type KbConversationStatus
} from "../../services/kbApi";

/**
 * Affiche si le mode conversation (STT + intents KB + Qdrant) est pret.
 */
export function VgConversationModeStatus() {
  const [status, setStatus] = useState<KbConversationStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const ac = new AbortController();
    void (async () => {
      try {
        const data = await fetchKbConversationStatus(ac.signal);
        if (ac.signal.aborted) return;
        setStatus(data);
        setError(null);
      } catch (exc) {
        if (isAbortError(exc) || ac.signal.aborted) return;
        setError(exc instanceof Error ? exc.message : "Statut conversation indisponible");
      } finally {
        if (!ac.signal.aborted) setLoading(false);
      }
    })();
    return () => ac.abort();
  }, []);

  if (loading) {
    return <CircularProgress size={20} />;
  }
  if (error) {
    return (
      <Alert severity="warning" sx={{ mt: 1 }}>
        {error}
      </Alert>
    );
  }
  if (!status) return null;

  const ready = Boolean(status.ready);
  const qdrantLine = status.qdrant_ok
    ? `Qdrant OK (${status.qdrant_points ?? 0} points).`
    : status.qdrant_configured
      ? `Qdrant KO${status.qdrant_detail ? ` - ${status.qdrant_detail}` : ""}.`
      : "Qdrant non configure (fallback local).";

  return (
    <Alert severity={ready ? "success" : "info"} sx={{ mt: 1 }}>
      <Typography variant="body2">
        {ready
          ? `Mode conversation pret (STT + intents). ${qdrantLine}`
          : `Mode conversation : verifie STT / intents KB avant usage. ${qdrantLine}`}
      </Typography>
    </Alert>
  );
}
