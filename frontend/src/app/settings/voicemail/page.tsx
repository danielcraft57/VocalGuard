"use client";

import React, { useCallback, useMemo } from "react";
import Link from "next/link";
import {
  Box,
  CircularProgress,
  FormControlLabel,
  Slider,
  Step,
  StepLabel,
  Stepper,
  Switch,
  TextField,
  Typography
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { AppLayout } from "../../../components/AppLayout";
import { VgAudioSourcePicker } from "../../../components/mui/VgAudioSourcePicker";
import { VgPageHeader } from "../../../components/mui/VgPageHeader";
import { VgSaveBar } from "../../../components/mui/VgSaveBar";
import { VgSettingsSection } from "../../../components/mui/VgSettingsSection";
import { useIncomingCallConfig } from "../../../hooks/useIncomingCallConfig";

type VoicemailBlock = {
  require_dtmf?: boolean;
  dtmf_digit?: string;
  dtmf_prompt_source?: "tts" | "wav";
  dtmf_prompt_text?: string;
  dtmf_timeout_sec?: number;
  max_record_sec?: number;
  silence_end_sec?: number;
};

const FLOW_STEPS = ["Accueil", "DTMF", "Bip", "Enregistrement", "Fin"];

/**
 * Parametres messagerie vocale et filtre DTMF anti-robots.
 */
export default function VoicemailSettingsPage() {
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
    save
  } = useIncomingCallConfig();

  const vm = useMemo(() => (config?.voicemail || {}) as VoicemailBlock, [config?.voicemail]);

  const patchVm = useCallback(
    (partial: Partial<VoicemailBlock>) => {
      if (!config) return;
      patchField("voicemail", { ...vm, ...partial });
    },
    [config, patchField, vm]
  );

  const activeStep = vm.require_dtmf ? 1 : 2;

  return (
    <AppLayout title="Messagerie et DTMF" hidePageHeader>
      <VgPageHeader
        title="Messagerie et DTMF"
        subtitle="Filtre anti-robots, duree d'enregistrement et fin sur silence."
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
            title="Flux repondeur"
            description="Etapes typiques apres decrochage (le DTMF est optionnel)."
          >
            <Stepper activeStep={activeStep} alternativeLabel sx={{ mb: 2 }}>
              {FLOW_STEPS.map((label) => (
                <Step key={label}>
                  <StepLabel>{label}</StepLabel>
                </Step>
              ))}
            </Stepper>
          </VgSettingsSection>

          <VgSettingsSection
            title="Filtre DTMF"
            description="Demande une touche avant d'enregistrer (bloque les robocalls muets)."
          >
            <FormControlLabel
              control={
                <Switch
                  checked={Boolean(vm.require_dtmf)}
                  onChange={(e) => patchVm({ require_dtmf: e.target.checked })}
                />
              }
              label="Exiger une touche DTMF"
            />
            {vm.require_dtmf ? (
              <Box sx={{ mt: 2, display: "flex", flexDirection: "column", gap: 2 }}>
                <TextField
                  size="small"
                  label="Touche attendue"
                  value={vm.dtmf_digit || "1"}
                  slotProps={{ htmlInput: { maxLength: 1 } }}
                  onChange={(e) => patchVm({ dtmf_digit: e.target.value.slice(0, 1) || "1" })}
                  helperText="0-9, * ou #"
                  sx={{ maxWidth: 160 }}
                />
                <VgAudioSourcePicker
                  label="Prompt DTMF"
                  source={vm.dtmf_prompt_source || "tts"}
                  onSourceChange={(v) => patchVm({ dtmf_prompt_source: v })}
                  wavPath=""
                  onWavPathChange={() => undefined}
                  ttsText={vm.dtmf_prompt_text || "Tapez 1 pour laisser un message."}
                  onTtsTextChange={(v) => patchVm({ dtmf_prompt_text: v })}
                />
                <Box>
                  <Typography variant="body2" gutterBottom>
                    Timeout DTMF : {vm.dtmf_timeout_sec ?? 8}s
                  </Typography>
                  <Slider
                    value={vm.dtmf_timeout_sec ?? 8}
                    min={2}
                    max={30}
                    step={1}
                    valueLabelDisplay="auto"
                    onChange={(_, v) => patchVm({ dtmf_timeout_sec: v as number })}
                  />
                </Box>
              </Box>
            ) : null}
          </VgSettingsSection>

          <VgSettingsSection
            title="Enregistrement"
            description="Duree max et coupure automatique apres silence."
          >
            <Box sx={{ mb: 3 }}>
              <Typography variant="body2" gutterBottom>
                Duree max : {vm.max_record_sec ?? 120}s
              </Typography>
              <Slider
                value={vm.max_record_sec ?? 120}
                min={10}
                max={600}
                step={10}
                valueLabelDisplay="auto"
                onChange={(_, v) => patchVm({ max_record_sec: v as number })}
              />
            </Box>
            <Box>
              <Typography variant="body2" gutterBottom>
                Fin sur silence : {vm.silence_end_sec ?? 4}s
              </Typography>
              <Slider
                value={vm.silence_end_sec ?? 4}
                min={1}
                max={30}
                step={0.5}
                valueLabelDisplay="auto"
                onChange={(_, v) => patchVm({ silence_end_sec: v as number })}
              />
            </Box>
          </VgSettingsSection>

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
