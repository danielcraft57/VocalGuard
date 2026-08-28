"use client";

import React, { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  CircularProgress,
  FormControlLabel,
  Slider,
  Switch,
  Typography
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { AppLayout } from "../../../components/AppLayout";
import { VgPageHeader } from "../../../components/mui/VgPageHeader";
import { VgSaveBar } from "../../../components/mui/VgSaveBar";
import { VgSettingsSection } from "../../../components/mui/VgSettingsSection";
import { useIncomingCallConfig } from "../../../hooks/useIncomingCallConfig";

type AdvancedBlock = {
  abort_answer_if_parallel_pickup?: boolean;
  blocked_play_message?: boolean;
  blocked_message_max_sec?: number;
  retry_greeting_on_fail?: boolean;
  prepare_voice_after_seize?: boolean;
};

/**
 * Reglages experts ligne entrante (cadence ring, abort parallele, JSON effectif).
 */
export default function IncomingAdvancedSettingsPage() {
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

  const [copied, setCopied] = useState(false);

  const advanced = useMemo(
    () => (config?.advanced || {}) as AdvancedBlock,
    [config?.advanced]
  );

  const patchAdvanced = useCallback(
    (partial: Partial<AdvancedBlock>) => {
      if (!config) return;
      patchField("advanced", { ...advanced, ...partial });
    },
    [advanced, config, patchField]
  );

  const effectiveJson = useMemo(() => {
    if (!config) return "";
    return JSON.stringify(config, null, 2);
  }, [config]);

  const copyJson = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(effectiveJson);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }, [effectiveJson]);

  return (
    <AppLayout title="Avance" hidePageHeader>
      <VgPageHeader
        title="Avance"
        subtitle="Cadence des sonneries, abort parallele et configuration effective."
        action={
          <Link href="/settings" style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <ArrowBackIcon fontSize="small" />
            <Typography variant="body2">Parametres</Typography>
          </Link>
        }
      />

      <Alert severity="warning" sx={{ mb: 2 }}>
        Reglages experts : modifier uniquement si tu sais ce que tu fais. Une mauvaise cadence ring
        peut faire rater des appels ou couper trop tot.
      </Alert>

      {loading || !config ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          <VgSettingsSection title="Timing CID et sonneries">
            <Box sx={{ mb: 3 }}>
              <Typography variant="body2" gutterBottom>
                Attente CID : {config.cid_wait_sec}s
              </Typography>
              <Slider
                value={config.cid_wait_sec ?? 2.5}
                min={0}
                max={30}
                step={0.5}
                valueLabelDisplay="auto"
                onChange={(_, v) => patchField("cid_wait_sec", v as number)}
              />
            </Box>
            <Box sx={{ mb: 3 }}>
              <Typography variant="body2" gutterBottom>
                Grace seize CID : {config.instant_seize_cid_grace_sec}s
              </Typography>
              <Slider
                value={config.instant_seize_cid_grace_sec ?? 0.35}
                min={0}
                max={5}
                step={0.05}
                valueLabelDisplay="auto"
                onChange={(_, v) => patchField("instant_seize_cid_grace_sec", v as number)}
              />
            </Box>
            <Box sx={{ mb: 3 }}>
              <Typography variant="body2" gutterBottom>
                Cycle ring : {config.ring_cycle_sec}s
              </Typography>
              <Slider
                value={config.ring_cycle_sec ?? 6}
                min={3}
                max={15}
                step={0.5}
                valueLabelDisplay="auto"
                onChange={(_, v) => patchField("ring_cycle_sec", v as number)}
              />
            </Box>
            <Box>
              <Typography variant="body2" gutterBottom>
                Silence avant abort (fixe parallele) : {config.ring_quiet_abort_sec}s
              </Typography>
              <Slider
                value={config.ring_quiet_abort_sec ?? 6}
                min={2}
                max={20}
                step={0.5}
                valueLabelDisplay="auto"
                onChange={(_, v) => patchField("ring_quiet_abort_sec", v as number)}
              />
            </Box>
          </VgSettingsSection>

          <VgSettingsSection title="Comportement expert">
            <FormControlLabel
              control={
                <Switch
                  checked={advanced.abort_answer_if_parallel_pickup !== false}
                  onChange={(e) =>
                    patchAdvanced({ abort_answer_if_parallel_pickup: e.target.checked })
                  }
                />
              }
              label="Abandonner si le fixe decroche en parallele"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={advanced.retry_greeting_on_fail !== false}
                  onChange={(e) => patchAdvanced({ retry_greeting_on_fail: e.target.checked })}
                />
              }
              label="Reessayer l'accueil si la lecture echoue"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={advanced.prepare_voice_after_seize !== false}
                  onChange={(e) =>
                    patchAdvanced({ prepare_voice_after_seize: e.target.checked })
                  }
                />
              }
              label="Preparer la ligne voix apres seize"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={advanced.blocked_play_message !== false}
                  onChange={(e) => patchAdvanced({ blocked_play_message: e.target.checked })}
                />
              }
              label="Jouer un message sur appels bloques"
            />
          </VgSettingsSection>

          <Accordion sx={{ mb: 2 }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography>Configuration effective (JSON)</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
                <Button
                  size="small"
                  startIcon={<ContentCopyIcon />}
                  onClick={() => void copyJson()}
                >
                  {copied ? "Copie !" : "Copier"}
                </Button>
              </Box>
              <Box
                component="pre"
                sx={{
                  p: 2,
                  bgcolor: "action.hover",
                  borderRadius: 1,
                  overflow: "auto",
                  fontSize: "0.75rem",
                  maxHeight: 360
                }}
              >
                {effectiveJson}
              </Box>
            </AccordionDetails>
          </Accordion>

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
