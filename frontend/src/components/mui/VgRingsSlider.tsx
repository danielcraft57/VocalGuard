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
 * Slider Material pour le nombre de sonneries (0-8).
 */
export function VgRingsSlider({
  label = "Sonneries",
  value,
  disabled = false,
  onChange
}: VgRingsSliderProps) {
  return (
    <>
      <Typography variant="body2" gutterBottom>
        {label} : {value}
      </Typography>
      <Slider
        value={value}
        min={0}
        max={8}
        step={1}
        marks
        disabled={disabled}
        valueLabelDisplay="auto"
        onChange={(_, v) => onChange(v as number)}
      />
    </>
  );
}
