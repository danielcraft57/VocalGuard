"use client";

import React, { useMemo, useRef, useState } from "react";
import { Box, CircularProgress, IconButton, Stack, Typography, useTheme } from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import PauseIcon from "@mui/icons-material/Pause";
import ReplayIcon from "@mui/icons-material/Replay";
import FastForwardIcon from "@mui/icons-material/FastForward";
import GraphicEqIcon from "@mui/icons-material/GraphicEq";
import { buildWaveformBars, waveformIndexAt } from "../utils/waveformBars";

const SKIP_SEC = 2;

type Props = {
  callId: number;
  currentTime: number;
  duration: number;
  playing: boolean;
  loading?: boolean;
  disabled?: boolean;
  /** Positions (sec) des cues pour marqueurs. */
  cueMarks?: number[];
  onTogglePlay: () => void;
  onSeek: (sec: number, playAfter?: boolean) => void;
  onSkip: (delta: number) => void;
  error?: string | null;
};

function formatClock(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0:00";
  const s = Math.floor(sec);
  const m = Math.floor(s / 60);
  return `${m}:${(s % 60).toString().padStart(2, "0")}`;
}

/**
 * Bande sonore : cadre haut, waveform, controles en calque semi-transparent (±2 s).
 */
export function CallSoundtrackBar({
  callId,
  currentTime,
  duration,
  playing,
  loading = false,
  disabled = false,
  cueMarks = [],
  onTogglePlay,
  onSeek,
  onSkip,
  error,
}: Props): React.ReactElement {
  const theme = useTheme();
  const waveRef = useRef<HTMLDivElement | null>(null);
  const [scrubbing, setScrubbing] = useState(false);
  const bars = useMemo(() => buildWaveformBars(callId * 17 + Math.round(duration), 64), [callId, duration]);
  const progress = duration > 0 ? Math.min(1, currentTime / duration) : 0;
  const filledUntil = waveformIndexAt(progress, bars.length);
  const primary = theme.palette.primary.main;
  const muted = theme.palette.mode === "dark" ? "rgba(148,163,184,0.38)" : "rgba(100,116,139,0.35)";
  const dark = theme.palette.mode === "dark";
  const blocked = disabled || loading;

  const seekFromClientX = (clientX: number, playAfter: boolean) => {
    const el = waveRef.current;
    if (!el || blocked || !Number.isFinite(duration) || duration <= 0) return;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0) return;
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    const target = ratio * duration;
    if (!Number.isFinite(target)) return;
    onSeek(target, playAfter);
  };

  return (
    <Box sx={{ px: 2, pb: 2, pt: 0.5 }}>
      <Stack direction="row" spacing={0.75} sx={{ mb: 1, color: "text.secondary", alignItems: "center" }}>
        <GraphicEqIcon sx={{ fontSize: 16 }} />
        <Typography variant="overline" sx={{ letterSpacing: "0.12em", lineHeight: 1 }}>
          Bande sonore
        </Typography>
      </Stack>

      {error ? (
        <Box
          sx={{
            height: 96,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderRadius: 3,
            border: "1px solid",
            borderColor: "divider",
            bgcolor: dark ? "rgba(15,20,28,0.55)" : "rgba(15,23,42,0.04)",
            px: 2,
          }}
        >
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
            {error}
          </Typography>
        </Box>
      ) : (
        <>
          <Box
            sx={{
              position: "relative",
              height: { xs: 128, sm: 148 },
              borderRadius: 3,
              border: "1px solid",
              borderColor: scrubbing ? "primary.main" : "divider",
              bgcolor: dark ? "rgba(15,20,28,0.55)" : "rgba(15,23,42,0.04)",
              overflow: "hidden",
              opacity: disabled && !loading ? 0.5 : 1,
            }}
          >
            <Box
              ref={waveRef}
              role="slider"
              aria-label="Position lecture"
              aria-valuemin={0}
              aria-valuemax={Math.round(duration)}
              aria-valuenow={Math.round(currentTime)}
              tabIndex={blocked ? -1 : 0}
              onKeyDown={(e) => {
                if (blocked || duration <= 0) return;
                if (e.key === "ArrowLeft") {
                  e.preventDefault();
                  onSkip(-SKIP_SEC);
                } else if (e.key === "ArrowRight") {
                  e.preventDefault();
                  onSkip(SKIP_SEC);
                }
              }}
              onPointerDown={(e) => {
                if (blocked) return;
                // Ne pas scrubber si le clic part d'un bouton du calque.
                const target = e.target as HTMLElement;
                if (target.closest("[data-ctrl]")) return;
                setScrubbing(true);
                (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
                seekFromClientX(e.clientX, false);
              }}
              onPointerMove={(e) => {
                if (!scrubbing) return;
                seekFromClientX(e.clientX, false);
              }}
              onPointerUp={(e) => {
                if (!scrubbing) return;
                setScrubbing(false);
                seekFromClientX(e.clientX, true);
              }}
              onPointerCancel={() => setScrubbing(false)}
              sx={{
                position: "absolute",
                inset: 0,
                display: "flex",
                alignItems: "flex-end",
                gap: "2px",
                cursor: blocked ? "default" : "pointer",
                px: 1.25,
                py: 2,
                touchAction: "none",
              }}
            >
              {bars.map((h, i) => {
                const played = i <= filledUntil;
                return (
                  <Box
                    key={`bar-${i}`}
                    sx={{
                      flex: 1,
                      height: `${Math.max(14, h * 100)}%`,
                      minHeight: 6,
                      borderRadius: 99,
                      bgcolor: played ? primary : muted,
                      opacity: played ? 1 : 0.75,
                      transition: scrubbing ? "none" : "background-color 0.12s ease",
                    }}
                  />
                );
              })}
              {cueMarks.map((mark, i) => {
                if (duration <= 0) return null;
                const left = `${Math.min(100, Math.max(0, (mark / duration) * 100))}%`;
                return (
                  <Box
                    key={`mark-${i}-${mark}`}
                    sx={{
                      position: "absolute",
                      left,
                      top: 10,
                      bottom: 10,
                      width: 2,
                      ml: "-1px",
                      borderRadius: 99,
                      bgcolor: "warning.main",
                      opacity: 0.55,
                      pointerEvents: "none",
                    }}
                  />
                );
              })}
            </Box>

            {/* Calque controles. */}
            <Stack
              direction="row"
              spacing={2}
              data-ctrl
              sx={{
                position: "absolute",
                inset: 0,
                alignItems: "center",
                justifyContent: "center",
                pointerEvents: "none",
              }}
            >
              <Stack
                direction="row"
                spacing={1.5}
                alignItems="center"
                sx={{
                  pointerEvents: "auto",
                  px: 1.75,
                  py: 1,
                  borderRadius: 999,
                  bgcolor: dark ? "rgba(15, 23, 42, 0.42)" : "rgba(255,255,255,0.55)",
                  border: "1px solid",
                  borderColor: dark ? "rgba(255,255,255,0.12)" : "rgba(15,23,42,0.08)",
                  backdropFilter: "blur(8px)",
                }}
              >
                <IconButton
                  data-ctrl
                  onClick={() => onSkip(-SKIP_SEC)}
                  disabled={blocked}
                  aria-label={`Reculer ${SKIP_SEC} secondes`}
                  size="small"
                  sx={{
                    bgcolor: dark ? "rgba(255,255,255,0.08)" : "rgba(15,23,42,0.06)",
                    borderRadius: 999,
                    px: 1,
                  }}
                >
                  <ReplayIcon fontSize="small" />
                  <Typography component="span" sx={{ ml: 0.25, fontWeight: 700, fontSize: 13 }}>
                    2
                  </Typography>
                </IconButton>

                <IconButton
                  data-ctrl
                  color="primary"
                  onClick={onTogglePlay}
                  disabled={blocked}
                  aria-label={playing ? "Pause" : "Lecture"}
                  sx={{
                    bgcolor: "primary.main",
                    color: "primary.contrastText",
                    width: 58,
                    height: 58,
                    opacity: 0.95,
                    boxShadow: 2,
                    "&:hover": { bgcolor: "primary.dark" },
                    "&.Mui-disabled": { bgcolor: "action.disabledBackground" },
                  }}
                >
                  {loading ? (
                    <CircularProgress size={26} color="inherit" />
                  ) : playing ? (
                    <PauseIcon fontSize="large" />
                  ) : (
                    <PlayArrowIcon fontSize="large" />
                  )}
                </IconButton>

                <IconButton
                  data-ctrl
                  onClick={() => onSkip(SKIP_SEC)}
                  disabled={blocked}
                  aria-label={`Avancer ${SKIP_SEC} secondes`}
                  size="small"
                  sx={{
                    bgcolor: dark ? "rgba(255,255,255,0.08)" : "rgba(15,23,42,0.06)",
                    borderRadius: 999,
                    px: 1,
                  }}
                >
                  <Typography component="span" sx={{ mr: 0.25, fontWeight: 700, fontSize: 13 }}>
                    2
                  </Typography>
                  <FastForwardIcon fontSize="small" />
                </IconButton>
              </Stack>
            </Stack>

            {loading ? (
              <Stack
                spacing={1}
                sx={{
                  position: "absolute",
                  inset: 0,
                  alignItems: "center",
                  justifyContent: "center",
                  bgcolor: dark ? "rgba(15, 23, 42, 0.55)" : "rgba(248,250,252,0.65)",
                  pointerEvents: "none",
                }}
              >
                <CircularProgress size={36} />
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                  Chargement audio...
                </Typography>
              </Stack>
            ) : null}
          </Box>

          <Stack direction="row" sx={{ mt: 0.75, justifyContent: "space-between" }}>
            <Typography variant="caption" sx={{ fontVariantNumeric: "tabular-nums", color: "text.secondary" }}>
              {formatClock(currentTime)}
            </Typography>
            <Typography variant="caption" sx={{ fontVariantNumeric: "tabular-nums", color: "text.secondary" }}>
              {formatClock(duration)}
            </Typography>
          </Stack>
        </>
      )}
    </Box>
  );
}
