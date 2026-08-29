"use client";

import React, { useCallback, useMemo } from "react";
import Link from "next/link";
import {
  Alert,
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

type GreetingIntroMode = "none" | "jingle" | "wav";

type AudioBlock = {
  greeting_source?: "tts" | "wav";
  greeting_wav_path?: string | null;
  greeting_tts_text?: string | null;
  greeting_intro_mode?: GreetingIntroMode;
  greeting_intro_wav_path?: string | null;
  greeting_intro_sec?: number;
  blocked_source?: "tts" | "wav";
  blocked_wav_path?: string | null;
  blocked_tts_text?: string | null;
  record_beep?: "wav" | "dtmf" | "none";
  record_beep_wav_path?: string | null;
  edge_tts_rate?: string;
  edge_tts_voice?: string;
  edge_tts_pitch?: string;
};

const EDGE_VOICES = [
  { id: "fr-FR-HenriNeural", label: "Henri (homme, professionnel)" },
  { id: "fr-FR-DeniseNeural", label: "Denise (femme)" },
  { id: "fr-FR-EloiseNeural", label: "Eloise (femme, douce)" },
  { id: "fr-FR-VivienneMultilingualNeural", label: "Vivienne (multilingue)" }
];

const DEFAULT_GREETING_HINT =
  'Ex. : Bonjour. <break time="400ms"/> Vous etes bien chez... Les balises <break> ameliorent le rythme.';

/**
 * Parametres messages vocaux : intro musicale, accueil TTS, bloque, bip.
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

  const audio = useMemo(() => (config?.audio || {}) as AudioBlock, [config?.audio]);

  const patchAudio = useCallback(
    (partial: Partial<AudioBlock>) => {
      if (!config) return;
      patchField("audio", { ...audio, ...partial });
    },
    [audio, config, patchField]
  );

  const rateNum = useMemo(() => {
    const raw = audio.edge_tts_rate || "+0%";
    const n = parseInt(raw.replace("%", "").replace("+", ""), 10);
    return Number.isFinite(n) ? n : 0;
  }, [audio.edge_tts_rate]);

  const pitchNum = useMemo(() => {
    const raw = audio.edge_tts_pitch || "+2Hz";
    const n = parseInt(raw.replace("Hz", "").replace("+", ""), 10);
    return Number.isFinite(n) ? n : 2;
  }, [audio.edge_tts_pitch]);

  const introMode = audio.greeting_intro_mode || "jingle";

  return (
    <AppLayout title="Messages et audio" hidePageHeader>
      <VgPageHeader
        title="Messages et audio"
        subtitle="Intro musicale, voix d'accueil et qualite TTS."
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
            title="Intro musicale"
            description="Courte musique avant la voix d'accueil (style standard repondeur pro)."
          >
            <FormControl size="small" fullWidth sx={{ mb: 2 }}>
              <InputLabel id="intro-mode">Intro</InputLabel>
              <Select
                labelId="intro-mode"
                label="Intro"
                value={introMode}
                onChange={(e) =>
                  patchAudio({ greeting_intro_mode: e.target.value as GreetingIntroMode })
                }
              >
                <MenuItem value="jingle">Jingle integre (recommande)</MenuItem>
                <MenuItem value="wav">Fichier WAV personnalise</MenuItem>
                <MenuItem value="none">Aucune intro</MenuItem>
              </Select>
            </FormControl>
            {introMode !== "none" ? (
              <>
                <Typography variant="body2" gutterBottom>
                  Duree max : {audio.greeting_intro_sec ?? 4}s
                </Typography>
                <Slider
                  value={audio.greeting_intro_sec ?? 4}
                  min={1}
                  max={12}
                  step={0.5}
                  valueLabelDisplay="auto"
                  onChange={(_, v) => patchAudio({ greeting_intro_sec: v as number })}
                />
                {introMode === "wav" ? (
                  <TextField
                    size="small"
                    fullWidth
                    sx={{ mt: 2 }}
                    label="Chemin WAV intro"
                    value={audio.greeting_intro_wav_path || "resources/voice/greeting_intro.wav"}
                    onChange={(e) =>
                      patchAudio({ greeting_intro_wav_path: e.target.value || null })
                    }
                    helperText="MP3/WAV converti cote serveur si besoin"
                  />
                ) : (
                  <Alert severity="info" sx={{ mt: 2 }}>
                    Le jingle est regenere au demarrage si absent (arpège doux 8 kHz).
                  </Alert>
                )}
              </>
            ) : null}
          </VgSettingsSection>

          <VgSettingsSection
            title="Voix d'accueil (TTS)"
            description="Qualite vocale Edge TTS — debit, voix et hauteur."
          >
            <FormControl size="small" fullWidth sx={{ mb: 2 }}>
              <InputLabel id="edge-voice">Voix</InputLabel>
              <Select
                labelId="edge-voice"
                label="Voix"
                value={audio.edge_tts_voice || "fr-FR-HenriNeural"}
                onChange={(e) => patchAudio({ edge_tts_voice: e.target.value })}
              >
                {EDGE_VOICES.map((v) => (
                  <MenuItem key={v.id} value={v.id}>
                    {v.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Typography variant="body2" gutterBottom>
              Debit : {rateNum > 0 ? `+${rateNum}%` : `${rateNum}%`}
            </Typography>
            <Slider
              value={rateNum}
              min={-20}
              max={25}
              step={1}
              valueLabelDisplay="auto"
              valueLabelFormat={(v) => `${v > 0 ? "+" : ""}${v}%`}
              onChange={(_, v) => {
                const n = v as number;
                patchAudio({ edge_tts_rate: `${n > 0 ? "+" : ""}${n}%` });
              }}
            />
            <Typography variant="body2" gutterBottom sx={{ mt: 2 }}>
              Hauteur : {pitchNum > 0 ? `+${pitchNum}` : pitchNum} Hz
            </Typography>
            <Slider
              value={pitchNum}
              min={-10}
              max={15}
              step={1}
              valueLabelDisplay="auto"
              valueLabelFormat={(v) => `${v > 0 ? "+" : ""}${v} Hz`}
              onChange={(_, v) => {
                const n = v as number;
                patchAudio({ edge_tts_pitch: `${n > 0 ? "+" : ""}${n}Hz` });
              }}
            />
          </VgSettingsSection>

          <VgSettingsSection
            title="Texte d'accueil"
            description="Joue apres l'intro musicale. Laisse vide pour le texte par defaut avec pauses."
          >
            <VgAudioSourcePicker
              label="Accueil"
              source={audio.greeting_source || "tts"}
              onSourceChange={(v) => patchAudio({ greeting_source: v })}
              wavPath={audio.greeting_wav_path || ""}
              onWavPathChange={(v) => patchAudio({ greeting_wav_path: v || null })}
              ttsText={audio.greeting_tts_text || ""}
              onTtsTextChange={(v) => patchAudio({ greeting_tts_text: v || null })}
              ttsPlaceholder={DEFAULT_GREETING_HINT}
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

          <VgSettingsSection title="Bip enregistrement" description="Apres le message d'accueil, avant l'enregistrement.">
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
