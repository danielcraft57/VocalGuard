"use client";

import React, { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import {
  Box,
  CircularProgress,
  FormControlLabel,
  Switch,
  Tab,
  Tabs,
  Typography
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { AppLayout } from "../../../components/AppLayout";
import {
  VgActionsBuilder,
  type IncomingAction
} from "../../../components/mui/VgActionsBuilder";
import { VgEffectiveConfigBanner } from "../../../components/mui/VgEffectiveConfigBanner";
import { VgPageHeader } from "../../../components/mui/VgPageHeader";
import { VgProfileChip } from "../../../components/mui/VgProfileChip";
import { VgRingsSlider } from "../../../components/mui/VgRingsSlider";
import { VgSaveBar } from "../../../components/mui/VgSaveBar";
import { VgSettingsSection } from "../../../components/mui/VgSettingsSection";
import { useIncomingCallConfig } from "../../../hooks/useIncomingCallConfig";

type ProfileKey = "permitted" | "screened" | "blocked";

type PresetShape = {
  permitted_actions?: IncomingAction[];
  screened_actions?: IncomingAction[];
  blocked_actions?: IncomingAction[];
  permitted_rings?: number;
  screened_rings?: number;
  blocked_rings?: number;
};

type ProfileOverride = {
  rings_before_answer?: number | null;
  actions?: IncomingAction[] | null;
  seize_on_ring?: boolean | null;
  require_cid_before_action?: boolean | null;
};

const PROFILE_TABS: { key: ProfileKey; label: string }[] = [
  { key: "permitted", label: "Autorises" },
  { key: "screened", label: "Inconnus" },
  { key: "blocked", label: "Bloques" }
];

function presetField(profile: ProfileKey, field: "actions" | "rings"): string {
  return field === "actions" ? `${profile}_actions` : `${profile}_rings`;
}

/**
 * Parametres par profil appelant (presets + overrides).
 */
export default function IncomingProfilesSettingsPage() {
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
  const [tab, setTab] = useState<ProfileKey>("screened");

  const preset = useMemo(() => {
    if (!config) return null;
    const p = config.presets?.[config.active_preset] as PresetShape | undefined;
    return p || null;
  }, [config]);

  const override = useMemo((): ProfileOverride => {
    if (!config) return {};
    const raw = config.profile_overrides?.[tab] as ProfileOverride | undefined;
    return raw || {};
  }, [config, tab]);

  const effectiveRings = useMemo(() => {
    if (override.rings_before_answer != null) return override.rings_before_answer;
    if (!preset) return 0;
    const key = presetField(tab, "rings") as keyof PresetShape;
    return Number(preset[key] ?? 0);
  }, [override, preset, tab]);

  const effectiveActions = useMemo((): IncomingAction[] => {
    if (override.actions && override.actions.length > 0) return override.actions;
    if (!preset) return ["ignore"];
    const key = presetField(tab, "actions") as keyof PresetShape;
    const list = preset[key];
    return (Array.isArray(list) ? list : ["ignore"]) as IncomingAction[];
  }, [override, preset, tab]);

  const patchOverride = useCallback(
    (partial: ProfileOverride) => {
      if (!config) return;
      const current = (config.profile_overrides || {}) as Record<string, ProfileOverride>;
      patchField("profile_overrides", {
        ...current,
        [tab]: { ...current[tab], ...partial }
      });
    },
    [config, patchField, tab]
  );

  const clearOverride = useCallback(() => {
    if (!config) return;
    const current = { ...(config.profile_overrides || {}) } as Record<string, ProfileOverride>;
    delete current[tab];
    patchField("profile_overrides", current);
  }, [config, patchField, tab]);

  const ringsPreview = useMemo(() => {
    if (!config) return "";
    const cycle = Number(config.ring_cycle_sec ?? 6);
    const quiet = Number(config.ring_quiet_abort_sec ?? 6);
    if (effectiveRings <= 0) {
      return "Decrochage immediat (rings=0). En mode repondeur, le fixe parallele est coupe.";
    }
    return `Attente de ${effectiveRings} sonnerie(s) (~${Math.round(effectiveRings * cycle)}s max) avant decrochage. Abort si le fixe decroche (${quiet}s sans RING).`;
  }, [config, effectiveRings]);

  return (
    <AppLayout title="Profils appelants" hidePageHeader>
      <VgPageHeader
        title="Profils et sonneries"
        subtitle="Comportement par type d'appelant : autorises, inconnus, bloques."
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
          <VgEffectiveConfigBanner
            inheritedFrom={config.active_preset === "voicemail" ? "Repondeur" : "Telephone"}
            detail={`Preset actif : ${config.active_preset}. Les champs vides utilisent les valeurs du preset.`}
          />

          <Tabs
            value={tab}
            onChange={(_, v: ProfileKey) => setTab(v)}
            sx={{ mb: 2 }}
            variant="scrollable"
          >
            {PROFILE_TABS.map((t) => (
              <Tab
                key={t.key}
                value={t.key}
                label={
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <VgProfileChip profile={t.key} />
                    {t.label}
                  </Box>
                }
              />
            ))}
          </Tabs>

          <VgSettingsSection
            title={`Profil : ${PROFILE_TABS.find((t) => t.key === tab)?.label}`}
            description="Personnalise ce profil ou reinitialise pour heriter du preset."
          >
            <VgRingsSlider
              value={effectiveRings}
              onChange={(v) => patchOverride({ rings_before_answer: v })}
            />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {ringsPreview}
            </Typography>
            <Box sx={{ mt: 2 }}>
              <VgActionsBuilder
                value={effectiveActions}
                onChange={(actions) => patchOverride({ actions })}
              />
            </Box>
            <Box sx={{ mt: 2 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={override.seize_on_ring ?? false}
                    onChange={(e) =>
                      patchOverride({
                        seize_on_ring: e.target.checked ? true : null
                      })
                    }
                  />
                }
                label="Seize immediat au RING (override)"
              />
            </Box>
            <Box sx={{ mt: 1 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={override.require_cid_before_action ?? true}
                    onChange={(e) =>
                      patchOverride({
                        require_cid_before_action: e.target.checked
                      })
                    }
                  />
                }
                label="Exiger le Caller ID avant action"
              />
            </Box>
            <Typography
              variant="caption"
              color="primary"
              sx={{ display: "block", mt: 2, cursor: "pointer" }}
              onClick={clearOverride}
            >
              Reinitialiser ce profil (heriter du preset)
            </Typography>
          </VgSettingsSection>

          <VgSettingsSection
            title="Classification"
            description="Inconnus traites comme profil « Inconnu » (screened) par defaut."
          >
            <FormControlLabel
              control={
                <Switch
                  checked={config.screened_when_unknown}
                  onChange={(e) => patchField("screened_when_unknown", e.target.checked)}
                />
              }
              label="Numeros inconnus = profil Inconnu (sinon Autorise)"
            />
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
