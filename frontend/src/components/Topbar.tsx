"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Chip,
  IconButton,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
  Box
} from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import PhoneIcon from "@mui/icons-material/Phone";
import PhoneInTalkIcon from "@mui/icons-material/PhoneInTalk";
import RingVolumeIcon from "@mui/icons-material/RingVolume";
import VoicemailIcon from "@mui/icons-material/Voicemail";
import {
  fetchSettings,
  fetchTelephonyStatus,
  setIncomingLineMode,
  type IncomingLineMode,
  type TelephonyStatus
} from "../services/settingsApi";
import { VgProfileChip } from "./mui/VgProfileChip";
import { parseIncomingDecision } from "../utils/incomingDecision";

export interface TopbarProps {
  /** Titre de la page courante. */
  title: string;
  /** Callback pour le bouton menu (mobile). */
  onMenuClick?: () => void;
}

/**
 * Bandeau superieur Material : menu, switch mode ligne, titre, pastille modem.
 */
export const Topbar: React.FC<TopbarProps> = ({ title, onMenuClick }) => {
  const [mode, setMode] = useState<IncomingLineMode>("voicemail");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tel, setTel] = useState<TelephonyStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSettings()
      .then((s) => {
        if (!cancelled) setMode(s.incoming_line_mode || "voicemail");
      })
      .catch(() => {
        /* ignore */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      fetchTelephonyStatus()
        .then((s) => {
          if (!cancelled) setTel(s);
        })
        .catch(() => {
          if (!cancelled) {
            setTel({
              status: "unreachable",
              modem_initialized: false,
              incoming_line_mode: mode,
              in_call: false,
              relay_failures: 0,
              daemon_reachable: false
            });
          }
        });
    };
    tick();
    const id = window.setInterval(tick, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [mode]);

  const switchMode = useCallback(
    async (next: IncomingLineMode) => {
      if (busy || next === mode) return;
      setBusy(true);
      setError(null);
      try {
        const s = await setIncomingLineMode(next);
        setMode(s.incoming_line_mode);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Impossible de changer le mode");
      } finally {
        setBusy(false);
      }
    },
    [busy, mode]
  );

  const modeLabel =
    mode === "voicemail" ? "Repondeur (coupe sonnerie)" : "Telephone (fixe seul)";

  const modemOk = Boolean(tel?.modem_initialized);
  const modemLabel = !tel
    ? "Modem…"
    : tel.daemon_reachable === false
      ? "Daemon HS"
      : modemOk
        ? tel.in_call
          ? "En appel"
          : "Modem OK"
        : "Modem KO";
  const modemTitle = tel
    ? [
        `status=${tel.status}`,
        tel.modem_port ? `port=${tel.modem_port}` : null,
        tel.firmware_ati3 ? `fw=${tel.firmware_ati3}` : null,
        tel.last_cid_raw ? `cid=${tel.last_cid_raw}` : null,
        tel.last_incoming_decision ? `decision=${tel.last_incoming_decision}` : null,
        tel.last_error ? `err=${tel.last_error}` : null
      ]
        .filter(Boolean)
        .join(" | ")
    : "Chargement etat telephonie";

  const lastDecision = parseIncomingDecision(tel?.last_incoming_decision);

  return (
    <header className="vg-topbar">
      <div className="vg-topbar-left">
        {onMenuClick ? (
          <IconButton
            onClick={onMenuClick}
            aria-label="Ouvrir le menu"
            size="small"
            sx={{ color: "inherit", mr: 0.5 }}
          >
            <MenuIcon />
          </IconButton>
        ) : null}

        <ToggleButtonGroup
          exclusive
          size="small"
          value={mode}
          disabled={busy}
          onChange={(_, v: IncomingLineMode | null) => {
            if (v) void switchMode(v);
          }}
          aria-label="Mode prise d'appel"
          sx={{ mr: 1 }}
        >
          <ToggleButton value="voicemail" aria-label="Repondeur">
            <VoicemailIcon fontSize="small" sx={{ mr: { xs: 0, sm: 0.5 } }} />
            <Typography
              component="span"
              variant="button"
              sx={{ display: { xs: "none", sm: "inline" }, fontSize: "0.75rem" }}
            >
              Repondeur
            </Typography>
          </ToggleButton>
          <ToggleButton value="phone" aria-label="Telephone">
            <PhoneInTalkIcon fontSize="small" sx={{ mr: { xs: 0, sm: 0.5 } }} />
            <Typography
              component="span"
              variant="button"
              sx={{ display: { xs: "none", sm: "inline" }, fontSize: "0.75rem" }}
            >
              Telephone
            </Typography>
          </ToggleButton>
        </ToggleButtonGroup>

        <div className="vg-topbar-title">{title}</div>
      </div>

      <div className="vg-topbar-right">
        {error ? <span className="vg-topbar-mode-error">{error}</span> : null}
        <Tooltip title={modemTitle}>
          <Chip
            size="small"
            label={modemLabel}
            color={modemOk ? "success" : "error"}
            variant="outlined"
            sx={{ mr: 1 }}
          />
        </Tooltip>
        {lastDecision ? (
          <Tooltip title={tel?.last_incoming_decision || lastDecision.label}>
            <Box component="span" sx={{ mr: 1, display: "inline-flex" }}>
              <VgProfileChip profile={lastDecision.profile} />
            </Box>
          </Tooltip>
        ) : null}
        <Stack
          direction="row"
          spacing={0.5}
          className="vg-topbar-status"
          title={modeLabel}
          sx={{ alignItems: "center" }}
        >
          {mode === "voicemail" ? (
            <RingVolumeIcon fontSize="small" color="primary" />
          ) : (
            <PhoneIcon fontSize="small" color="primary" />
          )}
          <Typography
            variant="caption"
            className="vg-topbar-status-text"
            sx={{ display: { xs: "none", md: "inline" } }}
          >
            {mode === "voicemail" ? "Repondeur actif" : "Fixe actif"}
          </Typography>
        </Stack>
      </div>
    </header>
  );
};
