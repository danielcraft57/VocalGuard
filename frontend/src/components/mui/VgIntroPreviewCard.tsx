"use client";

import React, { useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Stack,
  Typography
} from "@mui/material";
import HeadphonesIcon from "@mui/icons-material/Headphones";
import MusicNoteIcon from "@mui/icons-material/MusicNote";
import StopIcon from "@mui/icons-material/Stop";
import {
  previewGreetingAudio,
  type GreetingAudience
} from "../../services/settingsApi";

export type VgIntroPreviewCardProps = {
  /** Bloc audio courant (formulaire). */
  audio: Record<string, unknown>;
  /** Audience active (Connus / Inconnus / Commerciaux). */
  audience: GreetingAudience;
  /** Resume du mode intro (Jingle, Piste…). */
  modeLabel: string;
};

/**
 * Panneau d'apercu intro (colonne droite), aligné sur le style du greeting.
 *
 * Ecoute locale « Intro seule » sans toucher au cache modem.
 */
export function VgIntroPreviewCard({
  audio,
  audience,
  modeLabel
}: VgIntroPreviewCardProps): React.ReactElement {
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  const stop = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setPlaying(false);
  };

  /**
   * Genere et joue l'apercu intro seule pour l'audience courante.
   */
  const handlePreview = async () => {
    setError(null);
    stop();
    setLoading(true);
    try {
      const blob = await previewGreetingAudio(audio, "intro", audience);
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      const el = new Audio(url);
      audioRef.current = el;
      el.onended = () => stop();
      el.onerror = () => {
        setError("Lecture impossible");
        stop();
      };
      await el.play();
      setPlaying(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Apercu intro impossible");
      stop();
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      sx={{
        p: 2,
        borderRadius: 2,
        bgcolor: "action.hover",
        border: 1,
        borderColor: "divider",
        position: { md: "sticky" },
        top: { md: 16 }
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
        <MusicNoteIcon color="primary" fontSize="small" />
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          Apercu intro
        </Typography>
      </Stack>

      <Typography variant="body2" sx={{ mb: 0.5, fontWeight: 600 }}>
        {modeLabel}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
        Coupe l&apos;intro a la duree configuree (placement voix). Pour le volume
        jingle / voix : utilise « Mix complet » puis regenere le modem.
      </Typography>

      <Button
        fullWidth
        variant="contained"
        color="primary"
        disabled={loading}
        startIcon={
          loading ? (
            <CircularProgress size={16} color="inherit" />
          ) : playing ? (
            <StopIcon />
          ) : (
            <HeadphonesIcon />
          )
        }
        onClick={() => {
          if (playing) stop();
          else void handlePreview();
        }}
        sx={{ textTransform: "none", fontWeight: 600 }}
      >
        {playing ? "Stop" : "Ecouter l'intro"}
      </Button>

      {error ? (
        <Alert severity="error" sx={{ mt: 1.5, py: 0 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}
    </Box>
  );
}
