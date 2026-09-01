"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Box,
  Button,
  Chip,
  Dialog,
  IconButton,
  LinearProgress,
  Typography,
  useTheme
} from "@mui/material";
import BlockIcon from "@mui/icons-material/Block";
import CallEndIcon from "@mui/icons-material/CallEnd";
import RingVolumeIcon from "@mui/icons-material/RingVolume";
import type { IncomingLiveCall, IncomingLivePhase } from "../hooks/useIncomingCallLive";
import { VgProfileChip, type IncomingProfileKind } from "./mui/VgProfileChip";
import { playIncomingAlertSound } from "../utils/telephonySounds";
import { hangupIncomingCall } from "../services/callsApi";

type Props = {
  live: IncomingLiveCall | null;
  onDismiss: () => void;
};

function phaseLabel(phase: IncomingLiveCall["phase"]): string {
  switch (phase) {
    case "ringing":
      return "Appel entrant";
    case "answered":
      return "En ligne";
    case "blocked":
      return "Appel bloque";
    case "ended":
      return "Fin d'appel";
    default:
      return "Appel";
  }
}

function phaseToProfile(phase: IncomingLivePhase): IncomingProfileKind | null {
  if (phase === "blocked") return "blocked";
  if (phase === "answered" || phase === "ended") return "permitted";
  if (phase === "ringing") return "screened";
  return null;
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

/**
 * Modale plein ecran Material pour un appel entrant (evenements WS).
 */
export function IncomingCallModal({ live, onDismiss }: Props): React.ReactElement {
  const theme = useTheme();
  const open = Boolean(live);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [hangingUp, setHangingUp] = useState(false);
  const [hangupError, setHangupError] = useState<string | null>(null);

  const displayNumber = useMemo(() => {
    if (!live) return "Inconnu";
    return live.phoneNumber || live.callerName || "Inconnu";
  }, [live]);

  useEffect(() => {
    if (!live || live.phase !== "ringing") return;
    playIncomingAlertSound();
    const id = window.setInterval(() => playIncomingAlertSound(), 2200);
    return () => window.clearInterval(id);
  }, [live?.callId, live?.phase]);

  useEffect(() => {
    if (!live || (live.phase !== "ringing" && live.phase !== "answered")) {
      setElapsedMs(0);
      return;
    }
    const tick = () => setElapsedMs(Date.now() - live.startedAt);
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [live?.callId, live?.phase, live?.startedAt]);

  useEffect(() => {
    if (!live) {
      setHangingUp(false);
      setHangupError(null);
    }
  }, [live?.callId]);

  const phase = live?.phase ?? "ringing";
  const isActive = phase === "ringing" || phase === "answered";

  const phaseColor =
    phase === "blocked"
      ? theme.palette.error.main
      : phase === "ended"
        ? theme.palette.text.secondary
        : theme.palette.primary.main;

  const PhaseIcon =
    phase === "blocked" ? BlockIcon : phase === "ended" ? CallEndIcon : RingVolumeIcon;
  const liveProfile = phaseToProfile(phase);

  const handleHangup = async () => {
    if (!live || hangingUp) return;
    setHangingUp(true);
    setHangupError(null);
    try {
      await hangupIncomingCall(live.callId);
      onDismiss();
    } catch (err) {
      setHangupError(err instanceof Error ? err.message : "Echec raccrochage");
      setHangingUp(false);
    }
  };

  useEffect(() => {
    if (!live || (live.phase !== "ringing" && live.phase !== "answered")) return;
    const id = window.setTimeout(() => onDismiss(), 45_000);
    return () => window.clearTimeout(id);
  }, [live?.callId, live?.phase, onDismiss]);

  return (
    <Dialog
      fullScreen
      open={open}
      onClose={onDismiss}
      aria-labelledby="vg-incoming-title"
      slotProps={{
        paper: {
          sx: {
            animation: "vg-incoming-fade 0.25s ease-out"
          }
        }
      }}
    >
      <Box
        sx={{
          minHeight: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          px: 3,
          py: 6,
          bgcolor: "background.default",
          textAlign: "center"
        }}
      >
        <Box
          sx={{
            width: 120,
            height: 120,
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            mb: 3,
            bgcolor: `${phaseColor}22`,
            animation: isActive ? "vg-incoming-ring 1.6s ease-in-out infinite" : "none",
            "@keyframes vg-incoming-ring": {
              "0%, 100%": { transform: "scale(1)", opacity: 1 },
              "50%": { transform: "scale(1.08)", opacity: 0.88 }
            }
          }}
        >
          <IconButton aria-hidden sx={{ color: phaseColor }} size="large">
            <PhaseIcon sx={{ fontSize: 56 }} />
          </IconButton>
        </Box>

        <Typography
          id="vg-incoming-title"
          variant="overline"
          color="text.secondary"
          gutterBottom
        >
          {phaseLabel(phase)}
        </Typography>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", justifyContent: "center", mb: 1 }}>
          <Chip label={phaseLabel(phase)} size="small" color="primary" variant="outlined" />
          {liveProfile ? <VgProfileChip profile={liveProfile} /> : null}
        </Box>

        {(phase === "ringing" || phase === "answered") && (
          <Typography
            variant="h4"
            component="p"
            sx={{
              fontVariantNumeric: "tabular-nums",
              fontWeight: 700,
              letterSpacing: "0.06em",
              mb: 1,
              animation: "vg-incoming-pop 0.35s ease-out"
            }}
          >
            {formatElapsed(elapsedMs)}
          </Typography>
        )}

        {phase === "ringing" ? (
          <LinearProgress sx={{ width: "100%", maxWidth: 280, my: 2, borderRadius: 2 }} />
        ) : null}

        <Typography variant="h3" component="h2" gutterBottom sx={{ fontWeight: 600 }}>
          {displayNumber}
        </Typography>
        {live?.callerName && live.phoneNumber ? (
          <Typography variant="h6" color="text.secondary" gutterBottom>
            {live.callerName}
          </Typography>
        ) : (
          <Typography variant="body1" color="text.secondary" gutterBottom>
            {phase === "answered"
              ? "Repondeur VocalGuard"
              : phase === "ringing"
                ? "Decrochage automatique..."
                : "\u00a0"}
          </Typography>
        )}

        {live ? (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
            Appel #{live.callId}
          </Typography>
        ) : null}

        <Box
          sx={{
            mt: 4,
            display: "flex",
            flexDirection: "column",
            gap: 2,
            alignItems: "center",
            width: "100%",
            maxWidth: 320
          }}
        >
          {isActive ? (
            <>
              {phase === "answered" ? (
                <Button
                  variant="contained"
                  color="error"
                  size="large"
                  fullWidth
                  disabled={hangingUp}
                  onClick={() => void handleHangup()}
                  startIcon={<CallEndIcon />}
                  sx={{
                    py: 1.5,
                    borderRadius: 999,
                    fontWeight: 700,
                    boxShadow: 4,
                    transition: "transform 0.15s ease",
                    "&:hover:not(:disabled)": { transform: "scale(1.02)" },
                    "&:active:not(:disabled)": { transform: "scale(0.98)" }
                  }}
                >
                  {hangingUp ? "Raccrochage..." : "Raccrocher"}
                </Button>
              ) : null}
              {hangupError ? (
                <Typography variant="body2" color="error.main">
                  {hangupError}
                </Typography>
              ) : null}
              <Typography variant="body2" color="text.secondary">
                {phase === "ringing"
                  ? "Sonnerie en cours — decrochage auto"
                  : "Messagerie active — raccrochez pour couper l'appel"}
              </Typography>
              <Button variant="outlined" size="large" fullWidth onClick={onDismiss}>
                Masquer
              </Button>
            </>
          ) : (
            <Button variant="contained" size="large" fullWidth onClick={onDismiss}>
              Fermer
            </Button>
          )}
        </Box>
      </Box>
    </Dialog>
  );
}
