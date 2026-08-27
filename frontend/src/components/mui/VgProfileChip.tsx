"use client";

import React from "react";
import { Chip, type ChipProps } from "@mui/material";

export type IncomingProfileKind = "permitted" | "screened" | "blocked";

const LABELS: Record<IncomingProfileKind, string> = {
  permitted: "Autorise",
  screened: "Inconnu",
  blocked: "Bloque"
};

const COLORS: Record<IncomingProfileKind, ChipProps["color"]> = {
  permitted: "success",
  screened: "warning",
  blocked: "error"
};

export type VgProfileChipProps = {
  profile: IncomingProfileKind;
  size?: ChipProps["size"];
};

/**
 * Chip Material colore par profil appelant.
 */
export function VgProfileChip({ profile, size = "small" }: VgProfileChipProps) {
  return <Chip label={LABELS[profile]} color={COLORS[profile]} size={size} variant="outlined" />;
}
