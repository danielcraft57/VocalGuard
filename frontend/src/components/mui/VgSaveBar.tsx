"use client";

import React from "react";
import { Alert, Box, Button, CircularProgress, Snackbar, Typography } from "@mui/material";

export type VgSaveBarProps = {
  saving?: boolean;
  dirty?: boolean;
  error?: string | null;
  success?: string | null;
  onSave: () => void;
  onDismissSuccess?: () => void;
  onDismissError?: () => void;
  /** Si true : pas de bouton, indicateur auto-save seulement. */
  autoSave?: boolean;
};

/**
 * Barre d'actions sticky pour enregistrer les parametres (manuel ou auto-save).
 */
export function VgSaveBar({
  saving = false,
  dirty = true,
  error = null,
  success = null,
  onSave,
  onDismissSuccess,
  onDismissError,
  autoSave = false
}: VgSaveBarProps) {
  const statusLabel = saving
    ? "Enregistrement…"
    : dirty
      ? "Modification en cours…"
      : success
        ? "Enregistre"
        : null;

  return (
    <>
      <Box
        sx={{
          position: "sticky",
          bottom: 16,
          display: "flex",
          justifyContent: "flex-end",
          alignItems: "center",
          gap: 1.5,
          mt: 2,
          zIndex: 2
        }}
      >
        {autoSave ? (
          statusLabel ? (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              {saving ? <CircularProgress size={16} /> : null}
              <Typography variant="body2" color="text.secondary">
                {statusLabel}
              </Typography>
            </Box>
          ) : null
        ) : (
          <Button
            variant="contained"
            color="primary"
            disabled={!dirty || saving}
            onClick={onSave}
          >
            {saving ? "Enregistrement…" : "Enregistrer"}
          </Button>
        )}
      </Box>
      <Snackbar open={Boolean(success)} autoHideDuration={2500} onClose={onDismissSuccess}>
        <Alert severity="success" onClose={onDismissSuccess} sx={{ width: "100%" }}>
          {success}
        </Alert>
      </Snackbar>
      <Snackbar open={Boolean(error)} autoHideDuration={6000} onClose={onDismissError}>
        <Alert severity="error" onClose={onDismissError} sx={{ width: "100%" }}>
          {error}
        </Alert>
      </Snackbar>
    </>
  );
}
