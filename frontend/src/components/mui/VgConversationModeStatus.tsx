"use client";

import React, { useEffect, useState } from "react";
import { Alert, CircularProgress, Typography } from "@mui/material";
import {
  fetchKbConversationStatus,
  type KbConversationStatus
} from "../../services/kbApi";

/**
 * Affiche si le mode conversation (STT + intents KB) est pret.
 */
export function VgConversationModeStatus() {
  const [status, setStatus] = useState<KbConversationStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await fetchKbConversationStatus();
        if (!cancelled) {
          setStatus(data);
          setError(null);
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "Statut conversation indisponible");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
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

  const ready = Boolean((status as { ready?: boolean }).ready);
  return (
    <Alert severity={ready ? "success" : "info"} sx={{ mt: 1 }}>
      <Typography variant="body2">
        {ready
          ? "Mode conversation pret (STT + intents)."
          : "Mode conversation : verifie STT / intents KB avant usage."}
      </Typography>
    </Alert>
  );
}
