"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography
} from "@mui/material";
import HeadphonesIcon from "@mui/icons-material/Headphones";
import StopIcon from "@mui/icons-material/Stop";
import {
  fetchElevenLabsVoices,
  previewElevenLabsVoice,
  type ElevenLabsVoiceOption,
  type ElevenLabsVoicesResponse
} from "../../services/settingsApi";

export type VgElevenLabsVoicePickerProps = {
  /** Provider courant (edge | elevenlabs). */
  provider: "edge" | "elevenlabs";
  /** Voice id ElevenLabs selectionne. */
  voiceId: string;
  /** Changement de provider. */
  onProviderChange: (provider: "edge" | "elevenlabs") => void;
  /** Changement de voice id. */
  onVoiceIdChange: (voiceId: string) => void;
  /** Selecteur Edge TTS (enfant, affiche si provider=edge). */
  edgeVoiceSelect: React.ReactNode;
};

/**
 * Selecteur moteur TTS Edge / ElevenLabs + liste de voix + ecoute courte.
 *
 * Economise le quota gratuit (texte d'apercu tres court).
 */
export function VgElevenLabsVoicePicker({
  provider,
  voiceId,
  onProviderChange,
  onVoiceIdChange,
  edgeVoiceSelect
}: VgElevenLabsVoicePickerProps): React.ReactElement {
  const [catalog, setCatalog] = useState<ElevenLabsVoicesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customId, setCustomId] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const data = await fetchElevenLabsVoices();
        if (!cancelled) setCatalog(data);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Impossible de charger les voix");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const voices: ElevenLabsVoiceOption[] = catalog?.voices || [];
  const knownIds = useMemo(() => new Set(voices.map((v) => v.voice_id)), [voices]);
  const selectValue = knownIds.has(voiceId) ? voiceId : "__custom__";

  const stopPreview = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setPreviewing(false);
  };

  /**
   * Ecoute un extrait court de la voix selectionnee.
   */
  const handlePreview = async () => {
    const id = (selectValue === "__custom__" ? customId || voiceId : voiceId).trim();
    if (!id) {
      setError("Choisis une voix ou colle un voice_id");
      return;
    }
    setError(null);
    stopPreview();
    setPreviewing(true);
    try {
      const blob = await previewElevenLabsVoice(id);
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      const el = new Audio(url);
      audioRef.current = el;
      el.onended = () => stopPreview();
      el.onerror = () => {
        setError("Lecture impossible");
        stopPreview();
      };
      await el.play();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Apercu ElevenLabs impossible");
      stopPreview();
    }
  };

  return (
    <Stack spacing={1.5}>
      <Typography variant="caption" color="text.secondary">
        Moteur TTS
      </Typography>
      <ToggleButtonGroup
        exclusive
        fullWidth
        size="small"
        value={provider}
        onChange={(_, value: "edge" | "elevenlabs" | null) => {
          if (value) onProviderChange(value);
        }}
        aria-label="Moteur TTS"
        sx={{
          "& .MuiToggleButton-root": { textTransform: "none", fontWeight: 600 }
        }}
      >
        <ToggleButton value="edge">Edge (gratuit, illimite)</ToggleButton>
        <ToggleButton value="elevenlabs">ElevenLabs (quota limite)</ToggleButton>
      </ToggleButtonGroup>

      {provider === "edge" ? (
        edgeVoiceSelect
      ) : (
        <Stack spacing={1.25}>
          {loading ? (
            <Box sx={{ display: "flex", justifyContent: "center", py: 1 }}>
              <CircularProgress size={22} />
            </Box>
          ) : null}

          {catalog?.warning ? (
            <Alert severity="info" sx={{ py: 0 }}>
              {catalog.warning}
            </Alert>
          ) : null}

          <FormControl size="small" fullWidth>
            <InputLabel id="el-voice">Voix ElevenLabs</InputLabel>
            <Select
              labelId="el-voice"
              label="Voix ElevenLabs"
              value={selectValue}
              onChange={(e) => {
                const v = e.target.value;
                if (v === "__custom__") {
                  setCustomId(voiceId && !knownIds.has(voiceId) ? voiceId : "");
                  return;
                }
                onVoiceIdChange(v);
              }}
            >
              {voices.map((v) => (
                <MenuItem key={v.voice_id} value={v.voice_id}>
                  {v.recommended_fr ? "★ " : ""}
                  {v.name}
                  {v.labels ? ` — ${v.labels}` : ""}
                </MenuItem>
              ))}
              <MenuItem value="__custom__">Autre voice_id (coller)…</MenuItem>
            </Select>
          </FormControl>

          {selectValue === "__custom__" ? (
            <TextField
              size="small"
              fullWidth
              label="Voice id ElevenLabs"
              value={customId || (!knownIds.has(voiceId) ? voiceId : "")}
              onChange={(e) => setCustomId(e.target.value)}
              onBlur={() => {
                const v = customId.trim();
                if (v) onVoiceIdChange(v);
              }}
              helperText="Depuis le dashboard ElevenLabs → Voice → Copy voice ID"
            />
          ) : null}

          <Button
            variant="outlined"
            color="secondary"
            startIcon={previewing ? <StopIcon /> : <HeadphonesIcon />}
            disabled={loading || !catalog?.configured}
            onClick={() => {
              if (previewing) stopPreview();
              else void handlePreview();
            }}
            sx={{ textTransform: "none", fontWeight: 600, alignSelf: "flex-start" }}
          >
            {previewing ? "Stop" : "Ecouter cette voix"}
          </Button>

          <Typography variant="caption" color="warning.main">
            Free tier : chaque ecoute consomme des caracteres. Prefere Edge pour les essais
            longs, ElevenLabs pour le rendu final.
          </Typography>
        </Stack>
      )}

      {error ? (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}
    </Stack>
  );
}
