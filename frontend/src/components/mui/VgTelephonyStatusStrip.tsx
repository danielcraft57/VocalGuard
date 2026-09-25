"use client";

import React from "react";
import { Alert, Box, Chip, Stack, Typography } from "@mui/material";
import PhoneInTalkIcon from "@mui/icons-material/PhoneInTalk";
import VoicemailIcon from "@mui/icons-material/Voicemail";
import { VgProfileChip } from "./VgProfileChip";
import { useTelephonyStatus } from "../../hooks/useTelephonyStatus";
import { parseIncomingDecision } from "../../utils/incomingDecision";

/**
 * Bandeau leger : mode ligne, modem et derniere decision policy.
 * Reutilise le meme poll/cache que la Topbar.
 */
export function VgTelephonyStatusStrip(): React.ReactElement {
  const tel = useTelephonyStatus(10000);

  const mode = tel?.incoming_line_mode || "voicemail";
  const modemOk = Boolean(tel?.modem_initialized);
  const decision = parseIncomingDecision(tel?.last_incoming_decision);

  return (
    <Alert
      severity={modemOk ? "info" : "warning"}
      icon={false}
      sx={{ mb: 2, py: 1.5 }}
    >
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1}
        sx={{ alignItems: { xs: "flex-start", sm: "center" }, flexWrap: "wrap" }}
      >
        <Typography variant="body2" color="text.secondary" sx={{ mr: 1 }}>
          Ligne entrante
        </Typography>
        <Chip
          size="small"
          icon={mode === "voicemail" ? <VoicemailIcon /> : <PhoneInTalkIcon />}
          label={mode === "voicemail" ? "Repondeur" : "Telephone"}
          color="primary"
          variant="outlined"
        />
        <Chip
          size="small"
          label={
            !tel
              ? "Modem…"
              : tel.daemon_reachable === false
                ? "Daemon HS"
                : modemOk
                  ? tel.in_call
                    ? "En appel"
                    : "Modem OK"
                  : "Modem KO"
          }
          color={modemOk ? "success" : "error"}
          variant="outlined"
        />
        {decision ? (
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              Derniere decision
            </Typography>
            <VgProfileChip profile={decision.profile} />
            <Typography variant="caption" color="text.secondary" title={tel?.last_incoming_decision || ""}>
              {decision.label}
            </Typography>
          </Box>
        ) : (
          <Typography variant="caption" color="text.secondary">
            Aucune decision recente
          </Typography>
        )}
      </Stack>
    </Alert>
  );
}
