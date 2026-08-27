"use client";

import React, { useCallback } from "react";
import Link from "next/link";
import {
  Alert,
  Box,
  CircularProgress,
  FormControlLabel,
  Slider,
  Stack,
  Switch,
  ToggleButton,
  ToggleButtonGroup,
  Typography
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { AppLayout } from "../../../components/AppLayout";
import { VgPageHeader } from "../../../components/mui/VgPageHeader";
import { VgSaveBar } from "../../../components/mui/VgSaveBar";
import { VgSettingsSection } from "../../../components/mui/VgSettingsSection";
import { useIncomingCallConfig } from "../../../hooks/useIncomingCallConfig";
import {
  setIncomingLineMode,
  type IncomingLineMode
} from "../../../services/settingsApi";

/**
 * Parametres ligne entrante (mode repondeur / telephone, whitelist, sonneries).
 */
export default function IncomingLineSettingsPage() {
  const {
    config,
    loading,
    saving,
    dirty,
    error,
    success,
    setError,
    setSuccess,
    patchField,
    save,
    reload
  } = useIncomingCallConfig();

  const switchMode = useCallback(
    async (mode: IncomingLineMode) => {
      if (!config || config.incoming_line_mode === mode) return;
      setError(null);
      try {
        await setIncomingLineMode(mode);
        await reload();
        setSuccess(mode === "voicemail" ? "Mode repondeur actif" : "Mode telephone actif");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Changement de mode impossible");
      }
    },
    [config, reload, setError, setSuccess]
  );

  return (
    <AppLayout title="Ligne entrante" hidePageHeader>
      <VgPageHeader
        title="Ligne entrante"
        subtitle="Repondeur coupe la sonnerie du fixe. Mode telephone laisse sonner le fixe parallele."
        action={
          <Link href="/settings" style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <ArrowBackIcon fontSize="small" />
            <Typography variant="body2">Parametres</Typography>
          </Link>
        }
      />

      {loading || !config ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          <VgSettingsSection
            title="Mode de prise d'appel"
            description="Identique au switch de la barre superieure. Persiste sur le Pi."
          >
            <ToggleButtonGroup
              exclusive
              value={config.incoming_line_mode}
              onChange={(_, v: IncomingLineMode | null) => {
                if (v) void switchMode(v);
              }}
              size="small"
              sx={{ mb: 2 }}
            >
              <ToggleButton value="voicemail">Repondeur</ToggleButton>
              <ToggleButton value="phone">Telephone</ToggleButton>
            </ToggleButtonGroup>
            <Alert severity="info" sx={{ mb: 0 }}>
              {config.incoming_line_mode === "voicemail"
                ? "Le modem decroche tout de suite (rings=0) pour couper la sonnerie et activer le repondeur VocalGuard."
                : "Le modem journalise l'appel sans decrocher : le telephone fixe gere la sonnerie."}
            </Alert>
          </VgSettingsSection>

          <VgSettingsSection
            title="Whitelist ring-only"
            description="Les numeros en liste blanche font sonner le fixe sans que le modem reponde."
          >
            <FormControlLabel
              control={
                <Switch
                  checked={config.whitelist_ring_only}
                  onChange={(e) => patchField("whitelist_ring_only", e.target.checked)}
                />
              }
              label="Laisser sonner le fixe pour les numeros autorises"
            />
          </VgSettingsSection>

          <VgSettingsSection
            title="Sonneries mode telephone"
            description="Nombre de sonneries laissees au fixe quand le mode Telephone est actif."
          >
            <Typography variant="body2" gutterBottom>
              {config.phone_mode_rings} sonnerie(s)
            </Typography>
            <Slider
              value={config.phone_mode_rings}
              min={0}
              max={8}
              step={1}
              marks
              valueLabelDisplay="auto"
              onChange={(_, v) => patchField("phone_mode_rings", v as number)}
              disabled={config.incoming_line_mode !== "phone"}
            />
          </VgSettingsSection>

          <VgSettingsSection
            title="Fenetre Caller ID"
            description="Delai d'attente du numero avant action (hors repondeur immediat rings=0)."
          >
            <Typography variant="body2" gutterBottom>
              {config.cid_wait_sec.toFixed(1)} s
            </Typography>
            <Slider
              value={config.cid_wait_sec}
              min={0.5}
              max={10}
              step={0.5}
              valueLabelDisplay="auto"
              onChange={(_, v) => patchField("cid_wait_sec", v as number)}
            />
          </VgSettingsSection>

          <Stack spacing={1} sx={{ mb: 2 }}>
            <Typography variant="caption" color="text.secondary">
              Valeurs effectives : rings={config.rings_before_answer}, auto_answer=
              {config.incoming_auto_answer ? "oui" : "non"}
            </Typography>
          </Stack>

          <VgSaveBar
            saving={saving}
            dirty={dirty}
            error={error}
            success={success}
            onSave={() => void save()}
            onDismissError={() => setError(null)}
            onDismissSuccess={() => setSuccess(null)}
          />
        </>
      )}
    </AppLayout>
  );
}
