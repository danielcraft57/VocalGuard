"use client";

import React from "react";
import {
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography
} from "@mui/material";

export type AudioSourceKind = "tts" | "wav";

export type VgAudioSourcePickerProps = {
  label: string;
  source: AudioSourceKind;
  onSourceChange: (source: AudioSourceKind) => void;
  wavPath: string;
  onWavPathChange: (path: string) => void;
  ttsText: string;
  onTtsTextChange: (text: string) => void;
  ttsMultiline?: boolean;
  disabled?: boolean;
};

/**
 * Selecteur source audio TTS ou fichier WAV (chemin relatif projet).
 */
export function VgAudioSourcePicker({
  label,
  source,
  onSourceChange,
  wavPath,
  onWavPathChange,
  ttsText,
  onTtsTextChange,
  ttsMultiline = true,
  disabled = false
}: VgAudioSourcePickerProps) {
  return (
    <Stack spacing={2}>
      <Typography variant="subtitle1">{label}</Typography>
      <FormControl size="small" fullWidth disabled={disabled}>
        <InputLabel id={`${label}-source`}>Source</InputLabel>
        <Select
          labelId={`${label}-source`}
          label="Source"
          value={source}
          onChange={(e) => onSourceChange(e.target.value as AudioSourceKind)}
        >
          <MenuItem value="tts">Synthese vocale (TTS)</MenuItem>
          <MenuItem value="wav">Fichier WAV</MenuItem>
        </Select>
      </FormControl>
      {source === "wav" ? (
        <TextField
          size="small"
          fullWidth
          label="Chemin WAV (relatif au projet)"
          value={wavPath}
          onChange={(e) => onWavPathChange(e.target.value)}
          placeholder="resources/voice/beep.wav"
          disabled={disabled}
          helperText="Ex. resources/voice/blocked_short.wav — 8 kHz mono recommande"
        />
      ) : (
        <TextField
          size="small"
          fullWidth
          label="Texte TTS"
          value={ttsText}
          onChange={(e) => onTtsTextChange(e.target.value)}
          disabled={disabled}
          multiline={ttsMultiline}
          minRows={ttsMultiline ? 3 : 1}
        />
      )}
    </Stack>
  );
}
