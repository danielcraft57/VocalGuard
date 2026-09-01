"use client";

import React, { useCallback, useMemo } from "react";
import Link from "next/link";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  Stack,
  TextField,
  Typography
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import MusicNoteIcon from "@mui/icons-material/MusicNote";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import SettingsVoiceIcon from "@mui/icons-material/SettingsVoice";
import { AppLayout } from "../../../components/AppLayout";
import { VgAudioSourcePicker } from "../../../components/mui/VgAudioSourcePicker";
import { VgGreetingPreviewPanel } from "../../../components/mui/VgGreetingPreviewPanel";
import { VgPageHeader } from "../../../components/mui/VgPageHeader";
import { VgSaveBar } from "../../../components/mui/VgSaveBar";
import { VgSettingsSection } from "../../../components/mui/VgSettingsSection";
import { useIncomingCallConfig } from "../../../hooks/useIncomingCallConfig";

type GreetingIntroMode = "none" | "jingle" | "wav" | "track";

type AudioBlock = {
  greeting_source?: "tts" | "wav";
  greeting_wav_path?: string | null;
  greeting_tts_text?: string | null;
  greeting_intro_mode?: GreetingIntroMode;
  greeting_intro_variant?: string;
  greeting_intro_crossfade_ms?: number;
  greeting_intro_voice_bed_db?: number;
  greeting_intro_bed_variant?: string | null;
  greeting_intro_wav_path?: string | null;
  greeting_intro_sec?: number;
  greeting_intro_track_duck_db?: number;
  greeting_intro_music_offset_sec?: number;
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
  { id: "fr-FR-DeniseNeural", label: "Denise (femme, neutre)" },
  { id: "fr-FR-EloiseNeural", label: "Eloise (femme, douce)" },
  { id: "fr-FR-VivienneMultilingualNeural", label: "Vivienne (femme, multilingue)" },
  { id: "fr-BE-CharlineNeural", label: "Charline (femme, Belgique)" },
  { id: "fr-CH-ArianeNeural", label: "Ariane (femme, Suisse)" },
  { id: "fr-CA-SylvieNeural", label: "Sylvie (femme, Quebec)" },
  { id: "fr-FR-HenriNeural", label: "Henri (homme, professionnel)" }
];

const DEFAULT_GREETING_HINT =
  "Bonjour, Monsieur Daniel est absent. Merci de laisser un message apres le bip.";

/**
 * Parametres messages vocaux : intro musicale, accueil TTS, apercu, bloque, bip.
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
    const raw = audio.edge_tts_pitch || "+7Hz";
    const n = parseInt(raw.replace("Hz", "").replace("+", ""), 10);
    return Number.isFinite(n) ? n : 7;
  }, [audio.edge_tts_pitch]);

  const introMode = audio.greeting_intro_mode || "jingle";
  const bedDb = audio.greeting_intro_voice_bed_db ?? -24;

  return (
    <AppLayout title="Messages et audio" hidePageHeader>
      <VgPageHeader
        title="Messages et audio"
        subtitle="Accueil, intro musicale, apercu et cache modem."
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
        <Stack spacing={2}>
          <VgSettingsSection
            title="Message d'accueil"
            description="Texte, voix TTS et apercu avant mise en ligne sur le modem."
            icon={<RecordVoiceOverIcon color="primary" fontSize="small" />}
          >
            <VgGreetingPreviewPanel
              audio={audio as Record<string, unknown>}
              dirty={dirty}
              onSaveBeforeRegenerate={save}
            />

            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
                gap: 2,
                mt: 2
              }}
            >
              <FormControl size="small" fullWidth>
                <InputLabel id="edge-voice">Voix</InputLabel>
                <Select
                  labelId="edge-voice"
                  label="Voix"
                  value={audio.edge_tts_voice || "fr-FR-VivienneMultilingualNeural"}
                  onChange={(e) => patchAudio({ edge_tts_voice: e.target.value })}
                >
                  {EDGE_VOICES.map((v) => (
                    <MenuItem key={v.id} value={v.id}>
                      {v.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <Stack spacing={1}>
                <Typography variant="caption" color="text.secondary">
                  Debit : {rateNum > 0 ? `+${rateNum}%` : `${rateNum}%`}
                </Typography>
                <Slider
                  size="small"
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
              </Stack>

              <Stack spacing={1}>
                <Typography variant="caption" color="text.secondary">
                  Hauteur : {pitchNum > 0 ? `+${pitchNum}` : pitchNum} Hz
                </Typography>
                <Slider
                  size="small"
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
              </Stack>
            </Box>

            <Box sx={{ mt: 2 }}>
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
            </Box>
          </VgSettingsSection>

          <Accordion defaultExpanded={introMode === "track"} disableGutters elevation={0} sx={{ border: 1, borderColor: "divider", borderRadius: 1, "&:before": { display: "none" } }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <MusicNoteIcon color="action" fontSize="small" />
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  Intro musicale
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                  {introMode === "track" ? "Piste + voix" : introMode}
                </Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <FormControl size="small" fullWidth sx={{ mb: 2 }}>
                <InputLabel id="intro-mode">Type d&apos;intro</InputLabel>
                <Select
                  labelId="intro-mode"
                  label="Type d'intro"
                  value={introMode}
                  onChange={(e) =>
                    patchAudio({ greeting_intro_mode: e.target.value as GreetingIntroMode })
                  }
                >
                  <MenuItem value="jingle">Jingle messagerie (recommande)</MenuItem>
                  <MenuItem value="track">Piste musicale (debut + annonce par-dessus)</MenuItem>
                  <MenuItem value="wav">Fichier WAV personnalise</MenuItem>
                  <MenuItem value="none">Aucune intro</MenuItem>
                </Select>
              </FormControl>

              {introMode !== "none" ? (
                <Box
                  sx={{
                    display: "grid",
                    gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
                    gap: 2
                  }}
                >
                  <Stack>
                    <Typography variant="caption" color="text.secondary">
                      {introMode === "track"
                        ? `Musique seule : ${audio.greeting_intro_sec ?? 0}s`
                        : `Duree intro : ${audio.greeting_intro_sec ?? 2.2}s`}
                    </Typography>
                    <Slider
                      size="small"
                      value={audio.greeting_intro_sec ?? (introMode === "track" ? 0 : 2.2)}
                      min={introMode === "track" ? 0 : 1}
                      max={introMode === "track" ? 20 : 12}
                      step={0.5}
                      onChange={(_, v) => patchAudio({ greeting_intro_sec: v as number })}
                    />
                  </Stack>
                  <Stack>
                    <Typography variant="caption" color="text.secondary">
                      Fondu voix : {audio.greeting_intro_crossfade_ms ?? 450} ms
                    </Typography>
                    <Slider
                      size="small"
                      value={audio.greeting_intro_crossfade_ms ?? 280}
                      min={200}
                      max={1200}
                      step={20}
                      onChange={(_, v) =>
                        patchAudio({ greeting_intro_crossfade_ms: v as number })
                      }
                    />
                  </Stack>

                  {introMode === "track" ? (
                    <>
                      <Stack>
                        <Typography variant="caption" color="text.secondary">
                          Ducking musique :{" "}
                          {(audio.greeting_intro_track_duck_db ?? 0) <= 0
                            ? "auto"
                            : `${audio.greeting_intro_track_duck_db} dB`}
                        </Typography>
                        <Slider
                          size="small"
                          value={audio.greeting_intro_track_duck_db ?? 0}
                          min={0}
                          max={24}
                          step={1}
                          onChange={(_, v) =>
                            patchAudio({ greeting_intro_track_duck_db: v as number })
                          }
                        />
                      </Stack>
                      <Stack>
                        <Typography variant="caption" color="text.secondary">
                          Offset piste : {audio.greeting_intro_music_offset_sec ?? 0}s
                        </Typography>
                        <Slider
                          size="small"
                          value={audio.greeting_intro_music_offset_sec ?? 0}
                          min={0}
                          max={60}
                          step={1}
                          onChange={(_, v) =>
                            patchAudio({ greeting_intro_music_offset_sec: v as number })
                          }
                        />
                      </Stack>
                      <TextField
                        size="small"
                        fullWidth
                        sx={{ gridColumn: { sm: "1 / -1" } }}
                        label="Piste musicale (MP3/WAV)"
                        value={
                          audio.greeting_intro_wav_path ||
                          "resources/voice/music/whispering_iceland.mp3"
                        }
                        onChange={(e) =>
                          patchAudio({ greeting_intro_wav_path: e.target.value || null })
                        }
                      />
                    </>
                  ) : (
                    <>
                      <Stack>
                        <Typography variant="caption" color="text.secondary">
                          Fond sous voix : {bedDb} dB
                        </Typography>
                        <Slider
                          size="small"
                          value={bedDb}
                          min={-30}
                          max={0}
                          step={1}
                          onChange={(_, v) =>
                            patchAudio({ greeting_intro_voice_bed_db: v as number })
                          }
                        />
                      </Stack>
                      {introMode === "jingle" ? (
                        <FormControl size="small" fullWidth>
                          <InputLabel id="intro-variant">Jingle</InputLabel>
                          <Select
                            labelId="intro-variant"
                            label="Jingle"
                            value={audio.greeting_intro_variant || "sting_marimba"}
                            onChange={(e) =>
                              patchAudio({ greeting_intro_variant: e.target.value })
                            }
                          >
                            <MenuItem value="sting_marimba">Marimba chaleureux</MenuItem>
                            <MenuItem value="sting_corporate">Corporate lumineux</MenuItem>
                            <MenuItem value="sting_startup">Startup electronique</MenuItem>
                            <MenuItem value="sting_acoustic">Acoustique positif</MenuItem>
                            <MenuItem value="sting_mini">Mini stinger court</MenuItem>
                          </Select>
                        </FormControl>
                      ) : (
                        <TextField
                          size="small"
                          fullWidth
                          label="Chemin intro WAV/MP3"
                          value={audio.greeting_intro_wav_path || "resources/voice/intros/default.wav"}
                          onChange={(e) =>
                            patchAudio({ greeting_intro_wav_path: e.target.value || null })
                          }
                        />
                      )}
                    </>
                  )}
                </Box>
              ) : null}
            </AccordionDetails>
          </Accordion>

          <Accordion disableGutters elevation={0} sx={{ border: 1, borderColor: "divider", borderRadius: 1, "&:before": { display: "none" } }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <SettingsVoiceIcon color="action" fontSize="small" />
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  Messages secondaires
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Bloque, bip
                </Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={3}>
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Appel bloque
                  </Typography>
                  <VgAudioSourcePicker
                    label="Bloque"
                    source={audio.blocked_source || "wav"}
                    onSourceChange={(v) => patchAudio({ blocked_source: v })}
                    wavPath={audio.blocked_wav_path || "resources/voice/system/blocked_short.wav"}
                    onWavPathChange={(v) => patchAudio({ blocked_wav_path: v || null })}
                    ttsText={audio.blocked_tts_text || ""}
                    onTtsTextChange={(v) => patchAudio({ blocked_tts_text: v || null })}
                    ttsMultiline={false}
                  />
                </Box>
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Bip enregistrement
                  </Typography>
                  <FormControl size="small" fullWidth sx={{ mb: 1 }}>
                    <InputLabel id="record-beep">Type</InputLabel>
                    <Select
                      labelId="record-beep"
                      label="Type"
                      value={audio.record_beep || "wav"}
                      onChange={(e) =>
                        patchAudio({ record_beep: e.target.value as AudioBlock["record_beep"] })
                      }
                    >
                      <MenuItem value="wav">Fichier WAV</MenuItem>
                      <MenuItem value="dtmf">Tonalite DTMF</MenuItem>
                      <MenuItem value="none">Aucun</MenuItem>
                    </Select>
                  </FormControl>
                  {(audio.record_beep || "wav") === "wav" ? (
                    <TextField
                      size="small"
                      fullWidth
                      label="Chemin WAV bip"
                      value={audio.record_beep_wav_path || "resources/voice/system/beep.wav"}
                      onChange={(e) =>
                        patchAudio({ record_beep_wav_path: e.target.value || null })
                      }
                    />
                  ) : null}
                </Box>
              </Stack>
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
        </Stack>
      )}
    </AppLayout>
  );
}
