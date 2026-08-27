"use client";

import React from "react";
import { Alert } from "@mui/material";

export type VgEffectiveConfigBannerProps = {
  inheritedFrom?: string;
  detail?: string;
};

/**
 * Bandeau indiquant la valeur effective (preset vs override).
 */
export function VgEffectiveConfigBanner({ inheritedFrom, detail }: VgEffectiveConfigBannerProps) {
  if (!inheritedFrom && !detail) return null;
  return (
    <Alert severity="info" sx={{ mb: 2 }}>
      {detail ||
        `Valeurs effectives heritees du preset « ${inheritedFrom} » sauf champs personnalises ci-dessous.`}
    </Alert>
  );
}
