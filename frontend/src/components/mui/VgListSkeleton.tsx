/**
 * Skeletons generiques pour listes / cartes / tableaux.
 */

"use client";

import React from "react";
import { Box, Skeleton, Stack } from "@mui/material";

/**
 * Placeholder cartes dashboard.
 */
export function VgCardsSkeleton({ count = 4 }: { count?: number }): React.ReactElement {
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr 1fr", md: `repeat(${Math.min(count, 4)}, 1fr)` },
        gap: 2
      }}
      aria-busy
      aria-label="Chargement"
    >
      {Array.from({ length: count }).map((_, i) => (
        <Box
          key={i}
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2,
            p: 2,
            bgcolor: "background.paper"
          }}
        >
          <Skeleton variant="text" width="55%" animation="wave" />
          <Skeleton variant="rounded" height={36} width="40%" animation="wave" sx={{ mt: 1 }} />
        </Box>
      ))}
    </Box>
  );
}

/**
 * Placeholder lignes de tableau / liste.
 */
export function VgTableSkeleton({
  rows = 6
}: {
  rows?: number;
}): React.ReactElement {
  return (
    <Stack spacing={1} aria-busy aria-label="Chargement de la liste">
      {Array.from({ length: rows }).map((_, i) => (
        <Box
          key={i}
          sx={{
            display: "flex",
            gap: 1.5,
            alignItems: "center",
            py: 1.25,
            px: 1.5,
            borderBottom: "1px solid",
            borderColor: "divider"
          }}
        >
          <Skeleton variant="circular" width={28} height={28} animation="wave" />
          <Skeleton variant="text" width="28%" animation="wave" />
          <Skeleton variant="text" width="18%" animation="wave" />
          <Box sx={{ flex: 1 }} />
          <Skeleton variant="rounded" width={64} height={22} animation="wave" />
        </Box>
      ))}
    </Stack>
  );
}

/**
 * Placeholder formulaire settings.
 */
export function VgFormSkeleton(): React.ReactElement {
  return (
    <Stack spacing={2} aria-busy aria-label="Chargement des reglage">
      <Skeleton variant="text" width={180} height={32} animation="wave" />
      <Skeleton variant="rounded" height={48} animation="wave" />
      <Skeleton variant="rounded" height={48} animation="wave" />
      <Skeleton variant="rounded" height={96} animation="wave" />
      <Skeleton variant="rounded" width={140} height={36} animation="wave" />
    </Stack>
  );
}
