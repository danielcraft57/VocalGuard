"use client";

import React from "react";
import { Alert, Box, Button, Snackbar } from "@mui/material";

export type VgSaveBarProps = {
  saving?: boolean;
  dirty?: boolean;
  error?: string | null;
  success?: string | null;
  onSave: () => void;
  onDismissSuccess?: () => void;
  onDismissError?: () => void;
};

/**
 * Barre d'actions sticky pour enregistrer les parametres.
 */
export function VgSaveBar({
  saving = false,
  dirty = true,
  error = null,
  success = null,
  onSave,
  onDismissSuccess,
  onDismissError
}: VgSaveBarProps) {
  return (
    <>
      <Box
        sx={{
          position: "sticky",
          bottom: 16,
          display: "flex",
          justifyContent: "flex-end",
          gap: 1,
          mt: 2,
          zIndex: 2
        }}
      >
        <Button
          variant="contained"
          color="primary"
          disabled={!dirty || saving}
          onClick={onSave}
        >
          {saving ? "Enregistrement…" : "Enregistrer"}
        </Button>
      </Box>
      <Snackbar open={Boolean(success)} autoHideDuration={4000} onClose={onDismissSuccess}>
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
