"use client";

import React, { useMemo } from "react";
import {
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  Stack,
  Typography
} from "@mui/material";
import { VgElevenLabsVoicePicker } from "../mui/VgElevenLabsVoicePicker";
import type { KbVoicePrefs } from "../../services/kbUiPersist";

/** Voix Edge FR (meme catalogue que incoming-audio). */
export const KB_EDGE_VOICES = [
  { id: "fr-FR-DeniseNeural", label: "Denise (femme, neutre)" },
  { id: "fr-FR-EloiseNeural", label: "Eloise (femme, douce)" },
  { id: "fr-FR-VivienneMultilingualNeural", label: "Vivienne (femme, multilingue)" },
  { id: "fr-BE-CharlineNeural", label: "Charline (femme, Belgique)" },
  { id: "fr-CH-ArianeNeural", label: "Ariane (femme, Suisse)" },
  { id: "fr-CA-SylvieNeural", label: "Sylvie (femme, Quebec)" },
  { id: "fr-FR-HenriNeural", label: "Henri (homme, professionnel)" }
];

export type KbVoicePrefsPanelProps = {
  /** Prefs courantes. */
  value: KbVoicePrefs;
  /** Patch partiel. */
  onChange: (patch: Partial<KbVoicePrefs>) => void;
  /** Desactive les controles (regen en cours). */
  disabled?: boolean;
};

/**
 * Parse un rate Edge ``+12%`` / ``-5%``.
 *
 * @param raw Chaine config.
 * @returns Pourcentage entier.
 */
function parseRate(raw: string): number {
  const m = String(raw || "+0%").match(/([+-]?\d+)/);
  return m ? parseInt(m[1], 10) : 0;
}

/**
 * Parse un pitch Edge ``+7Hz`` / ``-2Hz``.
 *
 * @param raw Chaine config.
 * @returns Hertz entier.
 */
function parsePitch(raw: string): number {
  const m = String(raw || "+0Hz").match(/([+-]?\d+)/);
  return m ? parseInt(m[1], 10) : 0;
}

/**
 * Panneau voix TTS pour regen intents KB (provider, voix, volume, debit, hauteur).
 *
 * Inspire de /settings/incoming-audio.
 */
export function KbVoicePrefsPanel({
  value,
  onChange,
  disabled = false
}: KbVoicePrefsPanelProps): React.ReactElement {
  const rateNum = useMemo(() => parseRate(value.edge_tts_rate), [value.edge_tts_rate]);
  const pitchNum = useMemo(() => parsePitch(value.edge_tts_pitch), [value.edge_tts_pitch]);
  const gainDb = value.tts_voice_gain_db;

  return (
    <Stack spacing={2}>
      <VgElevenLabsVoicePicker
        provider={value.tts_provider}
        voiceId={value.elevenlabs_voice_id}
        onProviderChange={(p) => onChange({ tts_provider: p })}
        onVoiceIdChange={(id) =>
          onChange({ elevenlabs_voice_id: id, tts_provider: "elevenlabs" })
        }
        edgeVoiceSelect={
          <FormControl size="small" fullWidth disabled={disabled}>
            <InputLabel id="kb-edge-voice">Voix Edge</InputLabel>
            <Select
              labelId="kb-edge-voice"
              label="Voix Edge"
              value={value.edge_tts_voice}
              onChange={(e) => onChange({ edge_tts_voice: String(e.target.value) })}
            >
              {KB_EDGE_VOICES.map((v) => (
                <MenuItem key={v.id} value={v.id}>
                  {v.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        }
      />

      <Stack spacing={0.5}>
        <Typography variant="caption" color="text.secondary">
          Volume : {gainDb > 0 ? `+${gainDb}` : gainDb} dB
        </Typography>
        <Slider
          size="small"
          min={-18}
          max={6}
          step={1}
          value={gainDb}
          disabled={disabled}
          onChange={(_, v) => onChange({ tts_voice_gain_db: v as number })}
          valueLabelDisplay="auto"
        />
      </Stack>

      <Stack spacing={0.5}>
        <Typography variant="caption" color="text.secondary">
          Debit : {rateNum > 0 ? `+${rateNum}%` : `${rateNum}%`}
        </Typography>
        <Slider
          size="small"
          min={-50}
          max={50}
          step={5}
          value={rateNum}
          disabled={disabled || value.tts_provider !== "edge"}
          onChange={(_, v) => {
            const n = v as number;
            onChange({ edge_tts_rate: `${n > 0 ? "+" : ""}${n}%` });
          }}
          valueLabelDisplay="auto"
        />
      </Stack>

      <Stack spacing={0.5}>
        <Typography variant="caption" color="text.secondary">
          Hauteur : {pitchNum > 0 ? `+${pitchNum}` : pitchNum} Hz
        </Typography>
        <Slider
          size="small"
          min={-20}
          max={20}
          step={1}
          value={pitchNum}
          disabled={disabled || value.tts_provider !== "edge"}
          onChange={(_, v) => {
            const n = v as number;
            onChange({ edge_tts_pitch: `${n > 0 ? "+" : ""}${n}Hz` });
          }}
          valueLabelDisplay="auto"
        />
      </Stack>
    </Stack>
  );
}
