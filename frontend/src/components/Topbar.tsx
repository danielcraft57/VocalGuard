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
  setIncomingLineMode,
  type IncomingLineMode
} from "../services/settingsApi";
import { useTelephonyStatus } from "../hooks/useTelephonyStatus";
import {
  isAbortError,
  loadUiCache,
  saveUiCache,
  UI_CACHE_KEYS
} from "../services/uiPersist";
import { VgProfileChip } from "./mui/VgProfileChip";
import { parseIncomingDecision } from "../utils/incomingDecision";
import type { SettingsSnapshot } from "../services/settingsApi";

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
  const cachedSettings = loadUiCache<SettingsSnapshot>(UI_CACHE_KEYS.settingsSnapshot);
  const [mode, setMode] = useState<IncomingLineMode>(
    () => cachedSettings?.incoming_line_mode || "voicemail"
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tel = useTelephonyStatus(8000);

  useEffect(() => {
    const ac = new AbortController();
    fetchSettings(ac.signal)
      .then((s) => {
        setMode(s.incoming_line_mode || "voicemail");
        saveUiCache(UI_CACHE_KEYS.settingsSnapshot, s);
      })
      .catch((e) => {
        if (isAbortError(e)) return;
      });
    return () => ac.abort();
  }, []);

  const switchMode = useCallback(
    async (next: IncomingLineMode) => {
      if (busy || next === mode) return;
      setBusy(true);
      setError(null);
      try {
        const s = await setIncomingLineMode(next);
        setMode(s.incoming_line_mode);
        saveUiCache(UI_CACHE_KEYS.settingsSnapshot, s);
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
            className="vg-topbar-menu-button"
            onClick={onMenuClick}
            aria-label="Ouvrir le menu"
            size="small"
            sx={{ color: "inherit", mr: 0.5, display: { xs: "inline-flex", sm: "none" } }}
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
          sx={{ mr: 0.5, flexShrink: 0 }}
        >
          <ToggleButton value="voicemail" aria-label="Repondeur">
            <VoicemailIcon fontSize="small" sx={{ mr: { xs: 0, xl: 0.5 } }} />
            <Typography
              component="span"
              variant="button"
              sx={{ display: { xs: "none", xl: "inline" }, fontSize: "0.75rem" }}
            >
              Repondeur
            </Typography>
          </ToggleButton>
          <ToggleButton value="phone" aria-label="Telephone">
            <PhoneInTalkIcon fontSize="small" sx={{ mr: { xs: 0, xl: 0.5 } }} />
            <Typography
              component="span"
              variant="button"
              sx={{ display: { xs: "none", xl: "inline" }, fontSize: "0.75rem" }}
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
            sx={{ mr: 0.5, flexShrink: 0 }}
          />
        </Tooltip>
        {lastDecision ? (
          <Tooltip title={tel?.last_incoming_decision || lastDecision.label}>
            <Box component="span" sx={{ mr: 0.5, display: { xs: "none", md: "inline-flex" }, flexShrink: 0 }}>
              <VgProfileChip profile={lastDecision.profile} />
            </Box>
          </Tooltip>
        ) : null}
        <Stack
          direction="row"
          spacing={0.5}
          className="vg-topbar-status"
          title={modeLabel}
          sx={{ alignItems: "center", flexShrink: 0 }}
        >
          {mode === "voicemail" ? (
            <RingVolumeIcon fontSize="small" color="primary" />
          ) : (
            <PhoneIcon fontSize="small" color="primary" />
          )}
          <Typography
            variant="caption"
            className="vg-topbar-status-text"
            sx={{ display: { xs: "none", xl: "inline" }, whiteSpace: "nowrap" }}
          >
            {mode === "voicemail" ? "Repondeur actif" : "Fixe actif"}
          </Typography>
        </Stack>
      </div>
    </header>
  );
};
