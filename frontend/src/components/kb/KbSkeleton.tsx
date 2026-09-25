/**
 * Skeletons UX pour /kb et /simulator.
 */

"use client";

import React from "react";
import { Box, Skeleton, Stack } from "@mui/material";

/**
 * Placeholder liste d'intents (accordeons).
 *
 * @returns Skeleton.
 */
export function KbIntentsListSkeleton(): React.ReactElement {
  return (
    <Stack spacing={1.25} aria-busy="true" aria-label="Chargement des intents">
      {[0, 1, 2, 3].map((i) => (
        <Box
          key={i}
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            p: 1.5,
            bgcolor: "background.paper"
          }}
        >
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}>
            <Skeleton variant="rounded" width={120} height={22} animation="wave" />
            <Skeleton variant="rounded" width={48} height={20} animation="wave" />
            <Box sx={{ flex: 1 }} />
            <Skeleton variant="circular" width={28} height={28} animation="wave" />
          </Stack>
          <Skeleton variant="text" width="78%" animation="wave" />
          <Skeleton variant="text" width="42%" animation="wave" />
        </Box>
      ))}
    </Stack>
  );
}

/**
 * Placeholder historique + conversation tchatche.
 *
 * @returns Skeleton grille.
 */
export function KbTchatcheSkeleton(): React.ReactElement {
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", md: "280px 1fr" },
        gap: 2,
        minHeight: { md: "60vh" }
      }}
      aria-busy="true"
      aria-label="Chargement du simulateur"
    >
      <Box
        sx={{
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 2,
          p: 1.5,
          bgcolor: "background.paper"
        }}
      >
        <Skeleton variant="text" width={100} height={28} animation="wave" sx={{ mb: 1 }} />
        {[0, 1, 2, 3, 4].map((i) => (
          <Box key={i} sx={{ py: 1, borderBottom: "1px solid", borderColor: "divider" }}>
            <Skeleton variant="text" width="85%" animation="wave" />
            <Skeleton variant="text" width="45%" animation="wave" />
          </Box>
        ))}
      </Box>
      <Box
        sx={{
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 2,
          p: 2,
          bgcolor: "action.hover",
          display: "flex",
          flexDirection: "column",
          gap: 1.5
        }}
      >
        <Skeleton
          variant="rounded"
          width="70%"
          height={56}
          animation="wave"
          sx={{ alignSelf: "flex-start", borderRadius: 2 }}
        />
        <Skeleton
          variant="rounded"
          width="55%"
          height={48}
          animation="wave"
          sx={{ alignSelf: "flex-end", borderRadius: 2 }}
        />
        <Skeleton
          variant="rounded"
          width="65%"
          height={72}
          animation="wave"
          sx={{ alignSelf: "flex-start", borderRadius: 2 }}
        />
        <Box sx={{ flex: 1 }} />
        <Skeleton variant="rounded" height={40} animation="wave" />
      </Box>
    </Box>
  );
}

/**
 * Bandeau discret "sync en cours" (soft refresh avec cache deja affiche).
 *
 * @param props label optionnel.
 * @returns Chip animé.
 */
export function KbSoftSyncBar({
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
