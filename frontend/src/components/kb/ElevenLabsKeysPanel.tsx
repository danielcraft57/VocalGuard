"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Stack,
  Typography
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  activateElevenLabsKey,
  fetchElevenLabsKeysStatus,
  type ElevenLabsKeyQuota,
  type ElevenLabsKeysStatus
} from "../../services/settingsApi";

/**
 * Formate une date ISO / unix pour l'UI.
 *
 * @param iso ISO optionnel.
 * @param unix Unix optionnel.
 * @returns Texte court.
 */
function fmtDate(iso?: string | null, unix?: number | null): string {
  try {
    const d = iso ? new Date(iso) : unix ? new Date(unix * 1000) : null;
    if (!d || Number.isNaN(d.getTime())) return "—";
    return d.toLocaleString("fr-FR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch {
    return "—";
  }
}

/**
 * Panneau pool clefs ElevenLabs : quotas, reset, switch manuel.
 */
export function ElevenLabsKeysPanel(): React.ReactElement {
  const [status, setStatus] = useState<ElevenLabsKeysStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyFp, setBusyFp] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchElevenLabsKeysStatus(force);
      setStatus(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de charger le pool");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(true);
  }, [load]);

  const activate = useCallback(
    async (row: ElevenLabsKeyQuota) => {
      setBusyFp(row.fingerprint);
      setError(null);
      try {
        const data = await activateElevenLabsKey(row.fingerprint);
        setStatus(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Activation impossible");
      } finally {
        setBusyFp(null);
      }
    },
    []
  );

  return (
    <Stack spacing={1.25}>
      <Stack
        direction="row"
        spacing={1}
        sx={{ alignItems: "center", justifyContent: "space-between" }}
      >
        <Box>
          <Typography variant="subtitle2">Clefs ElevenLabs (pool)</Typography>
          <Typography variant="caption" color="text.secondary">
            Auto-switch si quota a 0. Active manuelle possible.
          </Typography>
        </Box>
        <Button
          size="small"
          startIcon={<RefreshIcon />}
          onClick={() => void load(true)}
          disabled={loading}
        >
          Rafraichir
        </Button>
      </Stack>

      {error ? <Alert severity="warning">{error}</Alert> : null}
      {loading && !status ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
          <CircularProgress size={22} />
        </Box>
      ) : null}

      {!loading && status && !status.keys.length ? (
        <Typography variant="body2" color="text.secondary">
          Aucune clef. Ajoute ``ELEVENLABS_API_KEYS`` (csv) dans ``.env``.
        </Typography>
      ) : null}

      <Stack spacing={1}>
        {(status?.keys || []).map((k) => (
          <Box
            key={k.fingerprint}
            sx={{
              p: 1.25,
              borderRadius: 1.25,
              border: "1px solid",
              borderColor: k.active ? "primary.main" : "divider",
              bgcolor: "background.paper"
            }}
          >
            <Stack
              direction={{ xs: "column", sm: "row" }}
              spacing={1}
              sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
            >
              <Box sx={{ minWidth: 0 }}>
                <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mb: 0.5 }}>
                  <Typography
                    variant="body2"
                    sx={{ fontFamily: "ui-monospace, monospace", fontWeight: 700 }}
                  >
                    {k.label}
                  </Typography>
                  {k.active ? <Chip size="small" color="primary" label="active" /> : null}
                  {k.ok ? (
                    <Chip size="small" variant="outlined" label={k.tier || k.status || "ok"} />
                  ) : (
                    <Chip size="small" color="error" label="erreur" />
                  )}
                </Stack>
                {k.ok && k.quota_readable ? (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                    Quota : {k.remaining ?? "?"} / {k.character_limit ?? "?"} restants
                    {" · "}used {k.character_count ?? "?"}
                    {" · "}reset {fmtDate(k.next_reset_iso, k.next_reset_unix)}
                  </Typography>
                ) : null}
                {k.ok && !k.quota_readable ? (
                  <Typography variant="caption" color="warning.main" sx={{ display: "block" }}>
                    {k.error ||
                      "Quota invisible : active User (Read) sur la clef. TTS fonctionne quand meme."}
                  </Typography>
                ) : null}
                {!k.ok ? (
                  <Typography variant="caption" color="error" sx={{ display: "block" }}>
                    {k.error || "Clef invalide"}
                  </Typography>
                ) : null}
                <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                  Compte cree : {fmtDate(k.created_at_iso, k.created_at_unix)}
                </Typography>
              </Box>
              <Button
                size="small"
                variant={k.active ? "outlined" : "contained"}
                disabled={Boolean(k.active) || busyFp === k.fingerprint || !k.ok}
                onClick={() => void activate(k)}
              >
                {busyFp === k.fingerprint ? "…" : k.active ? "En service" : "Utiliser"}
              </Button>
            </Stack>
          </Box>
        ))}
      </Stack>
    </Stack>
  );
}
