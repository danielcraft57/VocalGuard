"use client";

import React from "react";
import { Slider, Typography } from "@mui/material";

export type VgRingsSliderProps = {
  label?: string;
  value: number;
  disabled?: boolean;
  onChange: (value: number) => void;
};

/**
 * Slider Material pour le nombre de sonneries (-1 a 8).
 *
 * -1 = coupe sonnerie max (seize agressif, avant RING si CID meta).
 */
export function VgRingsSlider({
  label = "Sonneries",
  value,
  disabled = false,
  onChange
}: VgRingsSliderProps) {
  const display =
    value < 0 ? `${value} (coupe max)` : String(value);
  return (
    <>
      <Typography variant="body2" gutterBottom>
        {label} : {display}
      </Typography>
      <Slider
        value={value}
        min={-1}
        max={8}
        step={1}
        marks
        disabled={disabled}
        valueLabelDisplay="auto"
        valueLabelFormat={(v) => (v < 0 ? "max" : String(v))}
        onChange={(_, v) => onChange(v as number)}
      />
    </>
  );
}
