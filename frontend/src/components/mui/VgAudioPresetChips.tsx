"use client";

import React from "react";
import { Chip, CircularProgress, Stack, Tooltip, Typography } from "@mui/material";

export type AudioPresetOption = {
  id: string;
  label: string;
  description?: string;
  values: Record<string, unknown>;
};

export type VgAudioPresetChipsProps = {
  /** Titre court au-dessus des chips (ex. Prereglage voix). */
  title: string;
  /** Liste des presets disponibles. */
  presets: AudioPresetOption[];
  /** True pendant le chargement API. */
  loading?: boolean;
  /** Identifiant du dernier preset applique (surbrillance). */
  activePresetId?: string | null;
  /** Applique le patch audio du preset selectionne. */
  onApply: (preset: AudioPresetOption) => void;
};

/**
 * Rangée de chips pour appliquer un prereglage audio (voix, intro, outro).
 */
export function VgAudioPresetChips({
  title,
  presets,
  loading,
  activePresetId,
  onApply
}: VgAudioPresetChipsProps) {
  if (loading) {
    return (
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
        <Typography variant="caption" color="text.secondary">
          {title}
        </Typography>
        <CircularProgress size={14} />
      </Stack>
    );
  }

  if (!presets.length) {
    return null;
  }

  return (
    <Stack spacing={0.75} sx={{ mb: 2 }}>
      <Typography variant="caption" color="text.secondary">
        {title}
      </Typography>
      <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap" }}>
        {presets.map((preset) => {
          const selected = activePresetId === preset.id;
          const chip = (
            <Chip
              key={preset.id}
              size="small"
              label={preset.label}
              variant={selected ? "filled" : "outlined"}
              color={selected ? "primary" : "default"}
              onClick={() => onApply(preset)}
              sx={{ maxWidth: "100%" }}
            />
          );
          if (preset.description) {
            return (
              <Tooltip key={preset.id} title={preset.description} arrow>
                {chip}
              </Tooltip>
            );
          }
          return chip;
        })}
      </Stack>
    </Stack>
  );
}
