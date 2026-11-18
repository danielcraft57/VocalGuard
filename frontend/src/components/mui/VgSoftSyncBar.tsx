/**
 * Bandeau discret "sync en cours" (soft refresh avec cache deja affiche).
 */

"use client";

import React from "react";
import { Box } from "@mui/material";

/**
 * Chip sync anime.
 *
 * @param props label optionnel.
 */
export function VgSoftSyncBar({
  label = "Mise a jour…"
}: {
  label?: string;
}): React.ReactElement {
  return (
    <Box
      role="status"
      aria-live="polite"
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 1,
        px: 1.25,
        py: 0.5,
        borderRadius: 999,
        fontSize: "0.75rem",
        fontWeight: 600,
        color: "primary.main",
        bgcolor: "action.selected",
        border: "1px solid",
        borderColor: "divider"
      }}
    >
      <Box
        className="vg-page-loader-spinner"
        sx={{
          width: 14,
          height: 14,
          borderWidth: 2,
          flexShrink: 0
        }}
        aria-hidden
      />
      {label}
    </Box>
  );
}
