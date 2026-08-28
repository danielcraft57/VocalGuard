"use client";

import React, { useCallback, useMemo } from "react";
import Link from "next/link";
import {
  Box,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Slider,
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

type AudioBlock = {
  greeting_source?: "tts" | "wav";
  greeting_wav_path?: string | null;
  greeting_tts_text?: string | null;
  blocked_source?: "tts" | "wav";
  blocked_wav_path?: string | null;
  blocked_tts_text?: string | null;
  record_beep?: "wav" | "dtmf" | "none";
  record_beep_wav_path?: string | null;
  edge_tts_rate?: string;
};

/**
 * Parametres messages vocaux : accueil, bloque, bip (TTS ou WAV).
 */
export default function IncomingAudioSettingsPage() {
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

  const audio = useMemo(
    () => (config?.audio || {}) as AudioBlock,
    [config?.audio]
  );

  const patchAudio = useCallback(
    (partial: Partial<AudioBlock>) => {
      if (!config) return;
      patchField("audio", { ...audio, ...partial });
    },
    [audio, config, patchField]
  );

  const rateNum = useMemo(() => {
    const raw = audio.edge_tts_rate || "+12%";
    const n = parseInt(raw.replace("%", "").replace("+", ""), 10);
    return Number.isFinite(n) ? n : 12;
  }, [audio.edge_tts_rate]);

  return (
    <AppLayout title="Messages et audio" hidePageHeader>
      <VgPageHeader
        title="Messages et audio"
        subtitle="Accueil repondeur, message bloque et bip d'enregistrement."
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
            title="Message d'accueil"
            description="Joue au decrochage repondeur (profil inconnu ou autorise selon policy)."
          >
            <VgAudioSourcePicker
              label="Accueil"
              source={audio.greeting_source || "tts"}
              onSourceChange={(v) => patchAudio({ greeting_source: v })}
              wavPath={audio.greeting_wav_path || ""}
              onWavPathChange={(v) => patchAudio({ greeting_wav_path: v || null })}
              ttsText={audio.greeting_tts_text || ""}
              onTtsTextChange={(v) => patchAudio({ greeting_tts_text: v || null })}
            />
          </VgSettingsSection>

          <VgSettingsSection
            title="Message appel bloque"
            description="Court message avant raccrochage pour numeros bloques."
          >
            <VgAudioSourcePicker
              label="Bloque"
              source={audio.blocked_source || "wav"}
              onSourceChange={(v) => patchAudio({ blocked_source: v })}
              wavPath={audio.blocked_wav_path || "resources/voice/blocked_short.wav"}
              onWavPathChange={(v) => patchAudio({ blocked_wav_path: v || null })}
              ttsText={audio.blocked_tts_text || ""}
              onTtsTextChange={(v) => patchAudio({ blocked_tts_text: v || null })}
              ttsMultiline={false}
            />
          </VgSettingsSection>

          <VgSettingsSection title="Bip enregistrement" description="Avant l'enregistrement du message laisse.">
            <FormControl size="small" fullWidth sx={{ mb: 2 }}>
              <InputLabel id="record-beep">Type de bip</InputLabel>
              <Select
                labelId="record-beep"
                label="Type de bip"
                value={audio.record_beep || "wav"}
                onChange={(e) =>
                  patchAudio({ record_beep: e.target.value as AudioBlock["record_beep"] })
                }
              >
                <MenuItem value="wav">Fichier WAV</MenuItem>
                <MenuItem value="dtmf">Tonalite DTMF (1)</MenuItem>
                <MenuItem value="none">Aucun</MenuItem>
              </Select>
            </FormControl>
            {(audio.record_beep || "wav") === "wav" ? (
              <TextField
                size="small"
                fullWidth
                label="Chemin WAV bip"
                value={audio.record_beep_wav_path || "resources/voice/beep.wav"}
                onChange={(e) => patchAudio({ record_beep_wav_path: e.target.value || null })}
                helperText="Genere automatiquement au demarrage si absent"
              />
            ) : null}
          </VgSettingsSection>

          <VgSettingsSection title="Vitesse TTS" description="Edge TTS — s'applique aux messages en synthese vocale.">
            <Typography variant="body2" gutterBottom>
              {rateNum > 0 ? `+${rateNum}%` : `${rateNum}%`}
            </Typography>
            <Slider
              value={rateNum}
              min={-30}
              max={40}
              step={1}
              valueLabelDisplay="auto"
              valueLabelFormat={(v) => `${v > 0 ? "+" : ""}${v}%`}
              onChange={(_, v) => {
                const n = v as number;
                patchAudio({ edge_tts_rate: `${n > 0 ? "+" : ""}${n}%` });
              }}
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
