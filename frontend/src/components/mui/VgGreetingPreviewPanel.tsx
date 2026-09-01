"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  IconButton,
  LinearProgress,
  Stack,
  Tooltip,
  Typography
} from "@mui/material";
import GraphicEqIcon from "@mui/icons-material/GraphicEq";
import HeadphonesIcon from "@mui/icons-material/Headphones";
import PauseIcon from "@mui/icons-material/Pause";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  fetchGreetingAudioStatus,
  previewGreetingAudio,
  regenerateGreetingAudio,
  type GreetingAudioStatus
} from "../../services/settingsApi";

export type VgGreetingPreviewPanelProps = {
  /** Bloc audio courant du formulaire (meme non sauvegarde). */
  audio: Record<string, unknown>;
  /** True si des changements non enregistres existent. */
  dirty?: boolean;
  /** Enregistre le formulaire avant regen modem (si dirty). */
  onSaveBeforeRegenerate?: () => Promise<boolean>;
};

/**
 * Barre d'apercu / regeneration du message d'accueil (ecoute navigateur).
 */
export function VgGreetingPreviewPanel({
  audio,
  dirty,
  onSaveBeforeRegenerate
}: VgGreetingPreviewPanelProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const [status, setStatus] = useState<GreetingAudioStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [regenLoading, setRegenLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const revokeObjectUrl = useCallback(() => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const data = await fetchGreetingAudioStatus();
      setStatus(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de lire le cache accueil");
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    return () => revokeObjectUrl();
  }, [loadStatus, revokeObjectUrl]);

  const handlePreview = async () => {
    setError(null);
    setSuccess(null);
    setPreviewLoading(true);
    try {
      const blob = await previewGreetingAudio(audio);
      revokeObjectUrl();
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      const el = audioRef.current;
      if (el) {
        el.src = url;
        await el.play();
        setPlaying(true);
      }
      setSuccess("Apercu genere — lecture en cours");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Echec de l'apercu audio");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleRegenerate = async () => {
    setError(null);
    setSuccess(null);
    setRegenLoading(true);
    try {
      if (dirty && onSaveBeforeRegenerate) {
        const saved = await onSaveBeforeRegenerate();
        if (!saved) {
          setError("Enregistrement echoue — regeneration annulee");
          return;
        }
      }
      const data = await regenerateGreetingAudio(audio);
      setStatus(data);
      setSuccess(
        data.track_wav
          ? `Cache modem regenere : ${data.track_wav}`
          : "Cache modem regenere"
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Echec regeneration");
    } finally {
      setRegenLoading(false);
    }
  };

  const togglePlay = async () => {
    const el = audioRef.current;
    if (!el || !el.src) {
      await handlePreview();
      return;
    }
    if (playing) {
      el.pause();
      setPlaying(false);
    } else {
      await el.play();
      setPlaying(true);
    }
  };

  const busy = previewLoading || regenLoading;

  return (
    <Box
      sx={{
        p: 2,
        borderRadius: 2,
        bgcolor: "action.hover",
        border: 1,
        borderColor: "divider"
      }}
    >
      <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", flexWrap: "wrap" }} useFlexGap>
        <GraphicEqIcon color="primary" fontSize="small" />
        <Typography variant="subtitle2" sx={{ flex: 1, minWidth: 140 }}>
          Apercu et cache modem
        </Typography>
        {statusLoading ? (
          <CircularProgress size={20} />
        ) : status?.track_wav ? (
          <Chip
            size="small"
            variant="outlined"
            label={
              status.duration_sec
                ? `${status.track_wav} · ${status.duration_sec} s`
                : status.track_wav
            }
          />
        ) : (
          <Chip size="small" color="warning" variant="outlined" label="Cache absent" />
        )}
      </Stack>

      {dirty ? (
        <Alert severity="info" sx={{ mt: 1.5, py: 0 }}>
          Modifs non enregistrees : l&apos;apercu les prend en compte tout de suite.
          Regenerer enregistre d&apos;abord, puis met a jour le cache modem.
        </Alert>
      ) : null}

      {busy ? <LinearProgress sx={{ mt: 1.5, borderRadius: 1 }} /> : null}

      <Stack direction="row" spacing={1} sx={{ mt: 1.5, flexWrap: "wrap" }} useFlexGap>
        <Tooltip title="Generer et ecouter (qualite ecoute PC)">
          <span>
            <Button
              variant="contained"
              size="small"
              startIcon={
                previewLoading ? (
                  <CircularProgress size={16} color="inherit" />
                ) : (
                  <HeadphonesIcon />
                )
              }
              disabled={busy}
              onClick={() => void handlePreview()}
            >
              Ecouter l&apos;apercu
            </Button>
          </span>
        </Tooltip>

        <Tooltip title={objectUrlRef.current ? "Lecture / pause" : "Relancer l'apercu"}>
          <span>
            <IconButton
              size="small"
              color="primary"
              disabled={previewLoading}
              onClick={() => void togglePlay()}
              aria-label="Lecture pause"
            >
              {playing ? <PauseIcon /> : <PlayArrowIcon />}
            </IconButton>
          </span>
        </Tooltip>

        <Tooltip title="Enregistrer si besoin, puis regenerer le WAV sur le modem">
          <span>
            <Button
              variant="outlined"
              size="small"
              startIcon={
                regenLoading ? <CircularProgress size={16} /> : <RefreshIcon />
              }
              disabled={busy}
              onClick={() => void handleRegenerate()}
            >
              Regenerer sur le modem
            </Button>
          </span>
        </Tooltip>
      </Stack>

      {status?.voice ? (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
          Voix active : {status.voice.replace("fr-FR-", "")} · {status.pitch} · {status.rate}
        </Typography>
      ) : null}

      {error ? (
        <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}
      {success ? (
        <Alert severity="success" sx={{ mt: 1.5 }} onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      ) : null}

      <audio
        ref={audioRef}
        onEnded={() => setPlaying(false)}
        onPause={() => setPlaying(false)}
        onPlay={() => setPlaying(true)}
        style={{ display: "none" }}
      />
    </Box>
  );
}
