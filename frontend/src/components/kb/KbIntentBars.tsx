"use client";

import React, { useEffect, useState } from "react";
import { Box, LinearProgress, Stack, Typography } from "@mui/material";
import type { KbPredictItem } from "../../services/kbApi";

type Props = {
  preds: KbPredictItem[];
  /** Tag gagnant a mettre en avant */
  winner?: string | null;
  /** Declencheur pour relancer l'anim (id message) */
  animKey?: string;
  maxItems?: number;
};

/**
 * Barres de scores d'intents avec animation de remplissage.
 *
 * @param preds Predictions triees.
 * @param winner Tag commit / top.
 * @param animKey Cle pour rejouer l'anim.
 */
export function KbIntentBars({
  preds,
  winner,
  animKey,
  maxItems = 5
}: Props): React.ReactElement | null {
  const [ready, setReady] = useState(false);
  const slice = preds.slice(0, maxItems);

  useEffect(() => {
    setReady(false);
    const t = window.setTimeout(() => setReady(true), 40);
    return () => window.clearTimeout(t);
  }, [animKey, preds]);

  if (!slice.length) return null;

  return (
    <Stack spacing={0.75} sx={{ mt: 0.75, px: 0.5 }}>
      {slice.map((p, idx) => {
        const isWin = Boolean(winner && p.tag === winner);
        const pct = Math.max(0, Math.min(100, p.score * 100));
        return (
          <Box
            key={`${animKey || "b"}-${p.tag}`}
            sx={{
              opacity: ready ? 1 : 0,
              transform: ready ? "translateY(0)" : "translateY(6px)",
              transition: `opacity 280ms ease ${idx * 55}ms, transform 280ms ease ${idx * 55}ms`
            }}
          >
            <Stack direction="row" sx={{ justifyContent: "space-between", mb: 0.25 }}>
              <Typography
                variant="caption"
                sx={{ fontWeight: isWin ? 700 : 500, color: isWin ? "success.main" : "text.secondary" }}
              >
                {p.tag}
                {isWin ? " · choisi" : ""}
              </Typography>
              <Typography
                variant="caption"
                sx={{
                  fontVariantNumeric: "tabular-nums",
                  fontWeight: isWin ? 700 : 400
                }}
              >
                {Math.round(pct)}%
              </Typography>
            </Stack>
            <LinearProgress
              variant="determinate"
              value={ready ? pct : 0}
              sx={{
                height: isWin ? 8 : 5,
                borderRadius: 1,
                bgcolor: "action.hover",
                transition: "height 200ms ease",
                "& .MuiLinearProgress-bar": {
                  borderRadius: 1,
                  bgcolor: isWin ? "success.main" : "primary.main",
                  transition: `transform 700ms cubic-bezier(0.22, 1, 0.36, 1) ${idx * 70}ms`
                },
                ...(isWin
                  ? {
                      "@keyframes kbWinPulse": {
                        "0%, 100%": { boxShadow: "0 0 0 0 rgba(46, 125, 50, 0)" },
                        "50%": { boxShadow: "0 0 0 3px rgba(46, 125, 50, 0.28)" }
                      },
                      animation: ready ? "kbWinPulse 1.1s ease 0.5s 1" : "none"
                    }
                  : {})
              }}
            />
          </Box>
        );
      })}
    </Stack>
  );
}
