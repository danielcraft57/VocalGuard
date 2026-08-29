"use client";

import React, { useEffect, useMemo } from "react";
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

/**
 * Modale plein ecran Material pour un appel entrant (evenements WS).
 */
export function IncomingCallModal({ live, onDismiss }: Props): React.ReactElement {
  const theme = useTheme();
  const open = Boolean(live);

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

  return (
    <Dialog
      fullScreen
      open={open}
      onClose={() => {
        if (!isActive) onDismiss();
      }}
      aria-labelledby="vg-incoming-title"
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
            animation: isActive ? "vg-pulse 1.6s ease-in-out infinite" : "none",
            "@keyframes vg-pulse": {
              "0%, 100%": { transform: "scale(1)", opacity: 1 },
              "50%": { transform: "scale(1.06)", opacity: 0.85 }
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
        <Chip label={phaseLabel(phase)} size="small" color="primary" variant="outlined" sx={{ mb: 1 }} />
        {liveProfile ? <VgProfileChip profile={liveProfile} /> : null}
        {phase === "ringing" ? (
          <LinearProgress sx={{ width: "100%", maxWidth: 280, my: 2 }} />
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
                ? "Identification en cours..."
                : "\u00a0"}
          </Typography>
        )}

        {live ? (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
            Appel #{live.callId}
          </Typography>
        ) : null}

        <Box sx={{ mt: 4, display: "flex", flexDirection: "column", gap: 1.5, alignItems: "center" }}>
          {isActive ? (
            <>
              <Typography variant="body2" color="text.secondary">
                {phase === "ringing"
                  ? "Decrochage automatique..."
                  : "Se ferme a la fin de l'appel"}
              </Typography>
              <Button variant="outlined" size="large" onClick={onDismiss}>
                Masquer
              </Button>
            </>
          ) : (
            <Button variant="contained" size="large" onClick={onDismiss}>
              Fermer
            </Button>
          )}
        </Box>
      </Box>
    </Dialog>
  );
}
