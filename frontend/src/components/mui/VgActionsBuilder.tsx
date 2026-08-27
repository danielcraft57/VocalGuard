"use client";

import React from "react";
import { Chip, Stack, Typography } from "@mui/material";

export const INCOMING_ACTIONS = [
  "ignore",
  "answer",
  "greeting",
  "record",
  "dtmf_gate",
  "hangup",
  "play_blocked"
] as const;

export type IncomingAction = (typeof INCOMING_ACTIONS)[number];

const ACTION_LABELS: Record<IncomingAction, string> = {
  ignore: "Ignorer (fixe sonne)",
  answer: "Decrocher",
  greeting: "Accueil",
  record: "Enregistrer",
  dtmf_gate: "Filtre DTMF",
  hangup: "Raccrocher",
  play_blocked: "Message bloque"
};

export type VgActionsBuilderProps = {
  value: IncomingAction[];
  onChange: (actions: IncomingAction[]) => void;
  disabled?: boolean;
};

/**
 * Selection d'actions pipeline (chips toggleables).
 */
export function VgActionsBuilder({ value, onChange, disabled }: VgActionsBuilderProps) {
  const toggle = (action: IncomingAction) => {
    if (disabled) return;
    if (value.includes(action)) {
      onChange(value.filter((a) => a !== action));
    } else {
      onChange([...value, action]);
    }
  };

  return (
    <Stack spacing={1}>
      <Typography variant="body2" color="text.secondary">
        Actions (ordre d'execution)
      </Typography>
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
        {INCOMING_ACTIONS.map((action) => {
          const selected = value.includes(action);
          return (
            <Chip
              key={action}
              label={ACTION_LABELS[action]}
              color={selected ? "primary" : "default"}
              variant={selected ? "filled" : "outlined"}
              onClick={() => toggle(action)}
              disabled={disabled}
            />
          );
        })}
      </Stack>
    </Stack>
  );
}
