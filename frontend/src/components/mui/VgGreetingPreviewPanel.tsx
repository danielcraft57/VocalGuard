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
import MusicNoteIcon from "@mui/icons-material/MusicNote";
import PauseIcon from "@mui/icons-material/Pause";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  fetchGreetingAudioStatus,
  previewGreetingAudio,
  regenerateGreetingAudio,
  type GreetingAudience,
  type GreetingAudioStatus,
  type GreetingPreviewMode
} from "../../services/settingsApi";

export type VgGreetingPreviewPanelProps = {
  /** Bloc audio courant du formulaire (meme non sauvegarde). */
  audio: Record<string, unknown>;
  /** Slot d'accueil (connu / inconnu / commercial). */
  audience?: GreetingAudience;
  /** True si des changements non enregistres existent. */
  dirty?: boolean;
  /** Enregistre le formulaire avant regen modem (si dirty). */
  onSaveBeforeRegenerate?: () => Promise<boolean>;
};

/**
 * Barre d'apercu / regeneration du message d'accueil (ecoute navigateur).
 *
 * Remonte le lecteur a chaque changement d'audience pour eviter de rejouer
 * le mix precedent.
 */
export function VgGreetingPreviewPanel({
  audio,
  audience = "unknown",
  dirty,
  onSaveBeforeRegenerate
}: VgGreetingPreviewPanelProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const audienceRef = useRef(audience);
  const [status, setStatus] = useState<GreetingAudioStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [regenLoading, setRegenLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const clearPlayer = useCallback(() => {
    const el = audioRef.current;
    if (el) {
      try {
        el.pause();
      } catch {
        /* ignore */
      }
      el.removeAttribute("src");
      el.load();
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setPlaying(false);
  }, []);

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    setError(null);
    try {
      const data = await fetchGreetingAudioStatus(audience);
      setStatus(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de lire le cache accueil");
    } finally {
      setStatusLoading(false);
    }
  }, [audience]);

  useEffect(() => {
    audienceRef.current = audience;
    clearPlayer();
    setSuccess(null);
    void loadStatus();
    return () => clearPlayer();
  }, [audience, clearPlayer, loadStatus]);

  const handlePreview = async (mode: GreetingPreviewMode = "full") => {
    const requestedAudience = audience;
    setError(null);
    setSuccess(null);
    setPreviewLoading(true);
    try {
      const blob = await previewGreetingAudio(audio, mode, requestedAudience);
      if (audienceRef.current !== requestedAudience) {
        return;
      }
      clearPlayer();
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      const el = audioRef.current;
      if (el) {
        el.src = url;
        await el.play();
        setPlaying(true);
      }
      const labels: Record<GreetingPreviewMode, string> = {
        full: "Mix complet",
        voice: "Voix seule",
        intro: "Intro seule"
      };
      setSuccess(`Apercu ${labels[mode]} (${requestedAudience}) — lecture en cours`);
    } catch (e) {
      if (audienceRef.current === requestedAudience) {
        setError(e instanceof Error ? e.message : "Echec de l'apercu audio");
      }
    } finally {
      if (audienceRef.current === requestedAudience) {
        setPreviewLoading(false);
      }
    }
  };

  const handleRegenerate = async () => {
    const requestedAudience = audience;
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
      const data = await regenerateGreetingAudio(audio, requestedAudience);
      if (audienceRef.current !== requestedAudience) {
        return;
      }
      setStatus(data);
      clearPlayer();
      setSuccess(
        data.track_wav
          ? `Cache ${requestedAudience} regenere : ${data.track_wav}`
          : `Cache ${requestedAudience} regenere`
      );
    } catch (e) {
      if (audienceRef.current === requestedAudience) {
        setError(e instanceof Error ? e.message : "Echec regeneration");
      }
    } finally {
      if (audienceRef.current === requestedAudience) {
        setRegenLoading(false);
      }
    }
  };

  const togglePlay = async () => {
    const el = audioRef.current;
    // Toujours regenerer l'apercu si pas de source valide pour CET onglet.
    if (!el || !el.src || !objectUrlRef.current) {
      await handlePreview("full");
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
          Apercu et cache modem — {audience}
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
          <Chip size="small" color="warning" variant="outlined" label="Cache absent — regenerer" />
        )}
      </Stack>

      {status?.text ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
          Texte actif : {status.text.length > 120 ? `${status.text.slice(0, 120)}…` : status.text}
        </Typography>
      ) : null}

      {dirty ? (
        <Alert severity="info" sx={{ mt: 1.5, py: 0 }}>
          Modifs non enregistrees : l&apos;apercu les prend en compte tout de suite.
          Regenerer enregistre d&apos;abord, puis met a jour le cache modem.
        </Alert>
      ) : null}

      {busy ? <LinearProgress sx={{ mt: 1.5, borderRadius: 1 }} /> : null}

      <Stack direction="row" spacing={1} sx={{ mt: 1.5, flexWrap: "wrap" }} useFlexGap>
        <Tooltip title="Mix intro + voix au format ligne (11 kHz, bande telephone)">
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
              onClick={() => void handlePreview("full")}
            >
              Mix complet
            </Button>
          </span>
        </Tooltip>

        <Tooltip title="TTS seul avec volume, debit et hauteur actuels">
          <span>
            <Button
              variant="outlined"
              size="small"
              startIcon={<RecordVoiceOverIcon />}
              disabled={busy}
              onClick={() => void handlePreview("voice")}
            >
              Voix seule
            </Button>
          </span>
        </Tooltip>

        <Tooltip title="Fichier MP3 source (hifi). Au telephone : bande 300-3400 Hz, 11 kHz.">
          <span>
            <Button
              variant="outlined"
              size="small"
              startIcon={<MusicNoteIcon />}
              disabled={busy}
              onClick={() => void handlePreview("intro")}
            >
              Intro seule
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
