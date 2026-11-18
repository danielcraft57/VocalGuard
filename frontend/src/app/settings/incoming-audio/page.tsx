"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Box,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  Stack,
  Tab,
  Tabs,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import MusicNoteIcon from "@mui/icons-material/MusicNote";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import BlockIcon from "@mui/icons-material/Block";
import CheckIcon from "@mui/icons-material/Check";
import PersonSearchIcon from "@mui/icons-material/PersonSearch";
import GraphicEqIcon from "@mui/icons-material/GraphicEq";
import LibraryMusicIcon from "@mui/icons-material/LibraryMusic";
import AudioFileIcon from "@mui/icons-material/AudioFile";
import DoNotDisturbAltIcon from "@mui/icons-material/DoNotDisturbAlt";
import DialpadIcon from "@mui/icons-material/Dialpad";
import WavesIcon from "@mui/icons-material/Waves";
import { AppLayout } from "../../../components/AppLayout";
import { VgAudioPresetChips } from "../../../components/mui/VgAudioPresetChips";
import { VgAudioSourcePicker } from "../../../components/mui/VgAudioSourcePicker";
import { VgBeepPatternEditor, type BeepNote } from "../../../components/mui/VgBeepPatternEditor";
import { VgCollapsibleAudioSection } from "../../../components/mui/VgCollapsibleAudioSection";
import { VgElevenLabsVoicePicker } from "../../../components/mui/VgElevenLabsVoicePicker";
import { VgGreetingPreviewPanel } from "../../../components/mui/VgGreetingPreviewPanel";
import { VgIntroPreviewCard } from "../../../components/mui/VgIntroPreviewCard";
import { VgJingleListenButton } from "../../../components/mui/VgJingleListenButton";
import { VgPageHeader } from "../../../components/mui/VgPageHeader";
import { VgSaveBar } from "../../../components/mui/VgSaveBar";
import { VgSoftSyncBar } from "../../../components/mui/VgSoftSyncBar";
import { VgFormSkeleton } from "../../../components/mui/VgListSkeleton";
import { VgSettingsSection } from "../../../components/mui/VgSettingsSection";
import { useIncomingCallConfig } from "../../../hooks/useIncomingCallConfig";
import {
  fetchGreetingJingles,
  fetchIncomingAudioPresets,
  type AudioPresetOption,
  type GreetingAudience,
  type GreetingJingleOption,
  type IncomingAudioPresetsCatalog
} from "../../../services/settingsApi";

type GreetingIntroMode = "none" | "jingle" | "wav" | "track";
type RecordBeepMode = "wav" | "dtmf" | "croche" | "none";
type TtsProvider = "edge" | "elevenlabs";

type BeepNoteRow = BeepNote;

type AudienceSlot = {
  greeting_source?: "tts" | "wav";
  greeting_wav_path?: string | null;
  greeting_tts_text?: string | null;
  tts_provider?: TtsProvider | null;
  elevenlabs_voice_id?: string | null;
  greeting_intro_mode?: GreetingIntroMode | null;
  greeting_intro_variant?: string | null;
  greeting_intro_crossfade_ms?: number | null;
  greeting_intro_voice_gain_db?: number | null;
  greeting_intro_voice_bed_db?: number | null;
  greeting_intro_bed_variant?: string | null;
  greeting_intro_wav_path?: string | null;
  greeting_intro_sec?: number | null;
  greeting_intro_track_duck_db?: number | null;
  greeting_intro_music_offset_sec?: number | null;
  edge_tts_rate?: string | null;
  edge_tts_voice?: string | null;
  edge_tts_pitch?: string | null;
  tts_voice_gain_db?: number | null;
};

type AudioBlock = {
  greeting_source?: "tts" | "wav";
  greeting_wav_path?: string | null;
  greeting_tts_text?: string | null;
  tts_provider?: TtsProvider;
  elevenlabs_voice_id?: string | null;
  greeting_intro_mode?: GreetingIntroMode;
  greeting_intro_variant?: string;
  greeting_intro_crossfade_ms?: number;
  greeting_intro_voice_gain_db?: number;
  greeting_intro_voice_bed_db?: number;
  greeting_intro_bed_variant?: string | null;
  greeting_intro_wav_path?: string | null;
  greeting_intro_sec?: number;
  greeting_intro_track_duck_db?: number;
  greeting_intro_music_offset_sec?: number;
  blocked_source?: "tts" | "wav";
  blocked_wav_path?: string | null;
  blocked_tts_text?: string | null;
  record_beep?: RecordBeepMode;
  record_beep_wav_path?: string | null;
  record_beep_bpm?: number;
  record_beep_gap_ms?: number;
  record_beep_notes?: BeepNoteRow[];
  edge_tts_rate?: string;
  edge_tts_voice?: string;
  edge_tts_pitch?: string;
  tts_voice_gain_db?: number;
  audiences?: Partial<Record<GreetingAudience, AudienceSlot>>;
};

const AUDIENCE_TABS: {
  id: GreetingAudience;
  label: string;
  hint: string;
  color: "success" | "warning" | "error";
  icon: React.ReactElement;
}[] = [
  {
    id: "known",
    label: "Connus",
    hint: "Message d'accueil pour les numeros en liste blanche.",
    color: "success",
    icon: <CheckIcon fontSize="small" />
  },
  {
    id: "unknown",
    label: "Inconnus",
    hint: "Message d'accueil pour les appels non reconnus.",
    color: "warning",
    icon: <PersonSearchIcon fontSize="small" />
  },
  {
    id: "commercial",
    label: "Commerciaux",
    hint: "Message court pour spam / demarchage.",
    color: "error",
    icon: <BlockIcon fontSize="small" />
  }
];

const INTRO_MODES: {
  id: GreetingIntroMode;
  label: string;
  hint: string;
  icon: React.ReactElement;
}[] = [
  {
    id: "jingle",
    label: "Jingle",
    hint: "Musique libre de droit avant / sous la voix",
    icon: <MusicNoteIcon fontSize="small" />
  },
  {
    id: "track",
    label: "Piste",
    hint: "Solo musical puis annonce par-dessus",
    icon: <LibraryMusicIcon fontSize="small" />
  },
  {
    id: "wav",
    label: "Fichier",
    hint: "WAV / MP3 personnalise",
    icon: <AudioFileIcon fontSize="small" />
  },
  {
    id: "none",
    label: "Aucune",
    hint: "Voix seule, pas d'intro",
    icon: <DoNotDisturbAltIcon fontSize="small" />
  }
];

const BEEP_MODES: {
  id: RecordBeepMode;
  label: string;
  hint: string;
  icon: React.ReactElement;
}[] = [
  {
    id: "wav",
    label: "WAV",
    hint: "Fichier bip classique modem",
    icon: <GraphicEqIcon fontSize="small" />
  },
  {
    id: "dtmf",
    label: "DTMF",
    hint: "Tonalite synthetique",
    icon: <DialpadIcon fontSize="small" />
  },
  {
    id: "croche",
    label: "Partition",
    hint: "Notes + rythmes (croche, triolet…)",
    icon: <WavesIcon fontSize="small" />
  },
  {
    id: "none",
    label: "Aucun",
    hint: "Enregistrement direct apres l'accueil",
    icon: <DoNotDisturbAltIcon fontSize="small" />
  }
];

const SLOT_FIELDS: (keyof AudienceSlot)[] = [
  "greeting_source",
  "greeting_wav_path",
  "greeting_tts_text",
  "tts_provider",
  "elevenlabs_voice_id",
  "greeting_intro_mode",
  "greeting_intro_variant",
  "greeting_intro_crossfade_ms",
  "greeting_intro_voice_gain_db",
  "greeting_intro_voice_bed_db",
  "greeting_intro_bed_variant",
  "greeting_intro_wav_path",
  "greeting_intro_sec",
  "greeting_intro_track_duck_db",
  "greeting_intro_music_offset_sec",
  "edge_tts_rate",
  "edge_tts_voice",
  "edge_tts_pitch",
  "tts_voice_gain_db"
];

const EDGE_VOICES = [
  { id: "fr-FR-DeniseNeural", label: "Denise (femme, neutre)" },
  { id: "fr-FR-EloiseNeural", label: "Eloise (femme, douce)" },
  { id: "fr-FR-VivienneMultilingualNeural", label: "Vivienne (femme, multilingue)" },
  { id: "fr-BE-CharlineNeural", label: "Charline (femme, Belgique)" },
  { id: "fr-CH-ArianeNeural", label: "Ariane (femme, Suisse)" },
  { id: "fr-CA-SylvieNeural", label: "Sylvie (femme, Quebec)" },
  { id: "fr-FR-HenriNeural", label: "Henri (homme, professionnel)" }
];

const DEFAULT_GREETING_HINTS: Record<GreetingAudience, string> = {
  known:
    "Bonjour. Vous etes bien chez Daniel Craft, de Loic Daniel. Merci de laisser votre message apres le bip.",
  unknown:
    "Bonjour, je ne connais pas votre numéro ! Merci de vous présenter et de laisser vos coordonnées.",
  commercial: "Desole, cet appel ne peut pas aboutir. Merci de ne pas rappeler pour du demarchage."
};

const INTRO_MODE_LABELS: Record<GreetingIntroMode, string> = {
  jingle: "Jingle",
  track: "Piste",
  wav: "Fichier",
  none: "Desactivee"
};

const BEEP_MODE_LABELS: Record<RecordBeepMode, string> = {
  wav: "WAV",
  dtmf: "DTMF",
  croche: "Partition",
  none: "Desactive"
};

const DEFAULT_BEEP_NOTES: BeepNoteRow[] = [
  { pitch: "G5", rhythm: "croche" },
  { pitch: "E5", rhythm: "croche" }
];

/**
 * Fusionne le bloc audio global avec le slot audience actif.
 *
 * @param audio Bloc audio settings.
 * @param audience Slot actif.
 * @returns Audio effectif pour l'editeur.
 */
function resolveEffectiveAudio(audio: AudioBlock, audience: GreetingAudience): AudioBlock {
  const slot = (audio.audiences?.[audience] || {}) as AudienceSlot;
  const merged: AudioBlock = { ...audio };
  for (const field of SLOT_FIELDS) {
    const value = slot[field];
    if (value !== undefined && value !== null) {
      (merged as Record<string, unknown>)[field] = value;
    }
  }
  return merged;
}

/**
 * Parametres messages vocaux : un accueil par type d'appelant + TTS/mix.
 */
export default function IncomingAudioSettingsPage() {
  const [audience, setAudience] = useState<GreetingAudience>("unknown");
  const [introExpanded, setIntroExpanded] = useState(false);
  const [beepExpanded, setBeepExpanded] = useState(true);
  const [jingles, setJingles] = useState<GreetingJingleOption[]>([]);
  const [jinglesLoading, setJinglesLoading] = useState(true);
  const [audioPresets, setAudioPresets] = useState<IncomingAudioPresetsCatalog>({
    voice: [],
    intro: [],
    outro: []
  });
  const [presetsLoading, setPresetsLoading] = useState(true);
  const [voicePresetId, setVoicePresetId] = useState<string | null>(null);
  const [introPresetId, setIntroPresetId] = useState<string | null>(null);
  const [beepPresetId, setBeepPresetId] = useState<string | null>(null);
  const [blockedPresetId, setBlockedPresetId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const rows = await fetchGreetingJingles();
        if (!cancelled) setJingles(rows);
      } catch {
        if (!cancelled) setJingles([]);
      } finally {
        if (!cancelled) setJinglesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const catalog = await fetchIncomingAudioPresets();
        if (!cancelled) setAudioPresets(catalog);
      } catch {
        if (!cancelled) {
          setAudioPresets({ voice: [], intro: [], outro: [] });
        }
      } finally {
        if (!cancelled) setPresetsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const {
    config,
    loading,
    syncing,
    saving,
    dirty,
    error,
    success,
    setError,
    setSuccess,
    patchField,
    save
  } = useIncomingCallConfig();

  const audioRoot = useMemo(() => (config?.audio || {}) as AudioBlock, [config?.audio]);
  const audio = useMemo(
    () => resolveEffectiveAudio(audioRoot, audience),
    [audioRoot, audience]
  );
  const activeTab = AUDIENCE_TABS.find((t) => t.id === audience) || AUDIENCE_TABS[1];

  const patchAudio = useCallback(
    (partial: Partial<AudioBlock>) => {
      if (!config) return;
      const slotPatch: Partial<AudienceSlot> = {};
      const rootPatch: Partial<AudioBlock> = {};
      for (const [key, value] of Object.entries(partial)) {
        if (SLOT_FIELDS.includes(key as keyof AudienceSlot)) {
          (slotPatch as Record<string, unknown>)[key] = value;
        } else {
          (rootPatch as Record<string, unknown>)[key] = value;
        }
      }
      const audiences = { ...(audioRoot.audiences || {}) };
      if (Object.keys(slotPatch).length > 0) {
        audiences[audience] = {
          ...(audiences[audience] || {}),
          ...slotPatch
        };
      }
      patchField("audio", {
        ...audioRoot,
        ...rootPatch,
        audiences
      });
    },
    [audioRoot, audience, config, patchField]
  );

  const applyAudioPreset = useCallback(
    (preset: AudioPresetOption, track: "voice" | "intro" | "beep" | "blocked") => {
      if (track === "beep") {
        const values = preset.values as Partial<AudioBlock>;
        patchAudio({
          record_beep: values.record_beep,
          record_beep_wav_path: values.record_beep_wav_path,
          record_beep_bpm: values.record_beep_bpm,
          record_beep_gap_ms: values.record_beep_gap_ms,
          record_beep_notes: values.record_beep_notes
        });
        setBeepPresetId(preset.id);
        return;
      }
      if (track === "blocked") {
        const values = preset.values as Partial<AudioBlock>;
        patchAudio({
          blocked_source: values.blocked_source,
          blocked_wav_path: values.blocked_wav_path,
          blocked_tts_text: values.blocked_tts_text
        });
        setBlockedPresetId(preset.id);
        return;
      }
      patchAudio(preset.values as Partial<AudioBlock>);
      if (track === "voice") setVoicePresetId(preset.id);
      if (track === "intro") setIntroPresetId(preset.id);
    },
    [patchAudio]
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

  const voiceGainDb = audio.tts_voice_gain_db ?? -6;
  const introMode = audio.greeting_intro_mode || "jingle";
  const beepMode = audio.record_beep || "wav";
  const bedDb = audio.greeting_intro_voice_bed_db ?? -18;

  useEffect(() => {
    if (introMode !== "none") setIntroExpanded(true);
  }, [introMode, audience]);

  useEffect(() => {
    if (beepMode === "croche") setBeepExpanded(true);
  }, [beepMode]);

  const beepPresets = useMemo(
    () =>
      audioPresets.outro.filter((p) =>
        [
          "classique_modem",
          "bip_dtmf",
          "croche_conversation",
          "triolet_clair",
          "double_croche_sec",
          "sans_bip"
        ].includes(p.id)
      ),
    [audioPresets.outro]
  );

  const beepNotes = useMemo((): BeepNoteRow[] => {
    const raw = audio.record_beep_notes;
    if (Array.isArray(raw) && raw.length > 0) {
      return raw.map((n) => ({
        pitch: String(n.pitch || "G5"),
        rhythm: (n.rhythm || "croche") as BeepNoteRow["rhythm"]
      }));
    }
    return DEFAULT_BEEP_NOTES;
  }, [audio.record_beep_notes]);

  const blockedPresets = useMemo(
    () =>
      audioPresets.outro.filter((p) =>
        ["classique_modem", "bloque_vocal", "discret_complet"].includes(p.id)
      ),
    [audioPresets.outro]
  );

  return (
    <AppLayout title="Messages et audio" hidePageHeader>
      <VgPageHeader
        title="Messages et audio"
        subtitle="Un message d'accueil par type d'appelant, avec TTS et mix modem."
        action={
          <Link href="/settings" style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <ArrowBackIcon fontSize="small" />
            <Typography variant="body2">Parametres</Typography>
          </Link>
        }
      />

      {syncing && config ? (
        <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
          <VgSoftSyncBar />
        </Box>
      ) : null}

      {loading && !config ? (
        <VgFormSkeleton />
      ) : config ? (
        <Stack spacing={2}>
          <Box
            sx={{
              border: 1,
              borderColor: "divider",
              borderRadius: 2,
              overflow: "hidden",
              bgcolor: "background.paper"
            }}
          >
            <Tabs
              value={audience}
              onChange={(_, value: GreetingAudience) => {
                setAudience(value);
                setVoicePresetId(null);
                setIntroPresetId(null);
              }}
              variant="fullWidth"
              textColor="inherit"
              indicatorColor="primary"
              sx={{
                minHeight: 56,
                "& .MuiTab-root": { minHeight: 56, textTransform: "none", fontWeight: 600 }
              }}
            >
              {AUDIENCE_TABS.map((tab) => (
                <Tab
                  key={tab.id}
                  value={tab.id}
                  icon={tab.icon}
                  iconPosition="start"
                  label={tab.label}
                  sx={{
                    color: audience === tab.id ? `${tab.color}.main` : "text.secondary"
                  }}
                />
              ))}
            </Tabs>
          </Box>

          <Typography variant="body2" color="text.secondary" sx={{ px: 0.5 }}>
            {activeTab.hint}
          </Typography>

          <VgSettingsSection
            title={`Message d'accueil — ${activeTab.label}`}
            description="Voix, texte TTS et apercu modem pour ce type d'appelant."
            icon={<RecordVoiceOverIcon color={activeTab.color} fontSize="small" />}
          >
            <VgAudioPresetChips
              title="Prereglage de voix"
              presets={audioPresets.voice}
              loading={presetsLoading}
              activePresetId={voicePresetId}
              onApply={(preset) => applyAudioPreset(preset, "voice")}
            />

            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", lg: "1.1fr 0.9fr" },
                gap: 2.5,
                alignItems: "start"
              }}
            >
              <Stack spacing={2}>
                <VgElevenLabsVoicePicker
                  provider={(audio.tts_provider as TtsProvider) || "edge"}
                  voiceId={
                    audio.elevenlabs_voice_id || "JBFqnCBsd6RMkjVDRZzb"
                  }
                  onProviderChange={(p) => patchAudio({ tts_provider: p })}
                  onVoiceIdChange={(id) =>
                    patchAudio({ elevenlabs_voice_id: id, tts_provider: "elevenlabs" })
                  }
                  edgeVoiceSelect={
                    <FormControl size="small" fullWidth>
                      <InputLabel id="edge-voice">Voix Edge</InputLabel>
                      <Select
                        labelId="edge-voice"
                        label="Voix Edge"
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
                  }
                />

                <Stack spacing={1}>
                  <Typography variant="caption" color="text.secondary">
                    Volume : {voiceGainDb > 0 ? `+${voiceGainDb}` : voiceGainDb} dB
                  </Typography>
                  <Slider
                    size="small"
                    value={voiceGainDb}
                    min={-18}
                    max={9}
                    step={1}
                    valueLabelDisplay="auto"
                    valueLabelFormat={(v) => `${v > 0 ? "+" : ""}${v} dB`}
                    onChange={(_, v) => {
                      patchAudio({ tts_voice_gain_db: v as number });
                    }}
                  />
                </Stack>

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
                    Ton : {pitchNum > 0 ? `+${pitchNum}` : pitchNum} Hz
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

                <VgAudioSourcePicker
                  label="Message d'accueil (TTS)"
                  source={audio.greeting_source || "tts"}
                  onSourceChange={(v) => patchAudio({ greeting_source: v })}
                  wavPath={audio.greeting_wav_path || ""}
                  onWavPathChange={(v) => patchAudio({ greeting_wav_path: v || null })}
                  ttsText={audio.greeting_tts_text || ""}
                  onTtsTextChange={(v) => patchAudio({ greeting_tts_text: v || null })}
                  ttsPlaceholder={DEFAULT_GREETING_HINTS[audience]}
                />
              </Stack>

              <VgGreetingPreviewPanel
                key={audience}
                audio={audioRoot as Record<string, unknown>}
                audience={audience}
                dirty={dirty}
                onSaveBeforeRegenerate={save}
              />
            </Box>
          </VgSettingsSection>

          <VgCollapsibleAudioSection
            title="Intro musicale"
            description="Ajouter une introduction musicale avant le message."
            icon={<MusicNoteIcon color="primary" fontSize="small" />}
            summary={INTRO_MODE_LABELS[introMode]}
            expanded={introExpanded}
            onExpandedChange={setIntroExpanded}
          >
            <VgAudioPresetChips
              title="Prereglage intro"
              presets={audioPresets.intro}
              loading={presetsLoading}
              activePresetId={introPresetId}
              onApply={(preset) => applyAudioPreset(preset, "intro")}
            />

            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
              Type d&apos;intro
            </Typography>
            <ToggleButtonGroup
              exclusive
              fullWidth
              size="small"
              value={introMode}
              onChange={(_, value: GreetingIntroMode | null) => {
                if (value) patchAudio({ greeting_intro_mode: value });
              }}
              aria-label="Type d intro"
              sx={{
                mb: 2,
                flexWrap: { xs: "wrap", sm: "nowrap" },
                "& .MuiToggleButton-root": {
                  textTransform: "none",
                  fontWeight: 600,
                  gap: 0.75,
                  py: 1
                }
              }}
            >
              {INTRO_MODES.map((mode) => (
                <ToggleButton
                  key={mode.id}
                  value={mode.id}
                  aria-label={mode.label}
                  title={mode.hint}
                  sx={{ flex: 1, minWidth: { xs: "50%", sm: 0 } }}
                >
                  {mode.icon}
                  {mode.label}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>

            {introMode !== "none" ? (
              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: { xs: "1fr", md: "1.35fr 1fr" },
                  gap: 2.5,
                  alignItems: "start"
                }}
              >
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
                    Fondu voix : {audio.greeting_intro_crossfade_ms ?? 280} ms
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
                      helperText="Apercu Intro (coupe) = placement voix. Volumes : Mix complet puis Regenerer modem."
                    />
                  </>
                ) : (
                  <>
                    <Stack>
                      <Typography variant="caption" color="text.secondary">
                        Voix sur jingle : +{audio.greeting_intro_voice_gain_db ?? 0} dB
                      </Typography>
                      <Slider
                        size="small"
                        value={audio.greeting_intro_voice_gain_db ?? 0}
                        min={0}
                        max={12}
                        step={1}
                        onChange={(_, v) =>
                          patchAudio({ greeting_intro_voice_gain_db: v as number })
                        }
                      />
                    </Stack>
                    <Stack>
                      <Typography variant="caption" color="text.secondary">
                        {introMode === "jingle" ? "Volume jingle sous la voix" : "Fond sous voix"} :{" "}
                        {bedDb} dB {bedDb >= -1 ? "(coupe / voix seule)" : ""}
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
                      <Stack
                        direction="row"
                        spacing={1}
                        sx={{ alignItems: "flex-start", gridColumn: { sm: "1 / -1" } }}
                      >
                        <FormControl size="small" sx={{ flex: 1, minWidth: 0 }}>
                          <InputLabel id="intro-variant">Jingle MusicScreen</InputLabel>
                          <Select
                            labelId="intro-variant"
                            label="Jingle MusicScreen"
                            value={audio.greeting_intro_variant || "tesla"}
                            onChange={(e) =>
                              patchAudio({ greeting_intro_variant: e.target.value })
                            }
                            disabled={jinglesLoading}
                          >
                            {jingles.map((j) => (
                              <MenuItem key={j.id} value={j.id}>
                                {j.label}
                                {j.duration_sec ? ` (${j.duration_sec} s)` : ""}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                        <VgJingleListenButton
                          jingleId={audio.greeting_intro_variant || "tesla"}
                          disabled={jinglesLoading}
                        />
                      </Stack>
                    ) : (
                      <TextField
                        size="small"
                        fullWidth
                        sx={{ gridColumn: { sm: "1 / -1" } }}
                        label="Chemin intro WAV/MP3"
                        value={
                          audio.greeting_intro_wav_path || "resources/voice/intros/default.wav"
                        }
                        onChange={(e) =>
                          patchAudio({ greeting_intro_wav_path: e.target.value || null })
                        }
                      />
                    )}
                  </>
                )}
                </Box>

                <VgIntroPreviewCard
                  audio={audioRoot as Record<string, unknown>}
                  audience={audience}
                  modeLabel={INTRO_MODE_LABELS[introMode]}
                />
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Pas d&apos;intro : le message TTS demarre tout de suite. Tu peux toujours
                ecouter « Voix seule » dans l&apos;apercu.
              </Typography>
            )}
          </VgCollapsibleAudioSection>

          <VgCollapsibleAudioSection
            title="Bip d'enregistrement"
            description="Signal joue apres l'accueil, juste avant que l'appelant laisse son message."
            icon={<NotificationsActiveIcon color="warning" fontSize="small" />}
            summary={BEEP_MODE_LABELS[beepMode]}
            expanded={beepExpanded}
            onExpandedChange={setBeepExpanded}
          >
            <VgAudioPresetChips
              title="Prereglage bip"
              presets={beepPresets}
              loading={presetsLoading}
              activePresetId={beepPresetId}
              onApply={(preset) => applyAudioPreset(preset, "beep")}
            />

            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
              Type de bip
            </Typography>
            <ToggleButtonGroup
              exclusive
              fullWidth
              size="small"
              value={beepMode}
              onChange={(_, value: RecordBeepMode | null) => {
                if (value) {
                  patchAudio({ record_beep: value });
                  setBeepPresetId(null);
                }
              }}
              aria-label="Type de bip"
              sx={{
                mb: 2,
                flexWrap: { xs: "wrap", sm: "nowrap" },
                "& .MuiToggleButton-root": {
                  textTransform: "none",
                  fontWeight: 600,
                  gap: 0.75,
                  py: 1
                }
              }}
            >
              {BEEP_MODES.map((mode) => (
                <ToggleButton
                  key={mode.id}
                  value={mode.id}
                  aria-label={mode.label}
                  title={mode.hint}
                  color={mode.id === "none" ? "standard" : "warning"}
                  sx={{ flex: 1, minWidth: { xs: "50%", sm: 0 } }}
                >
                  {mode.icon}
                  {mode.label}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>

            {beepMode === "wav" ? (
              <TextField
                size="small"
                fullWidth
                label="Chemin WAV bip"
                value={audio.record_beep_wav_path || "resources/voice/system/beep.wav"}
                onChange={(e) => {
                  patchAudio({ record_beep_wav_path: e.target.value || null });
                  setBeepPresetId(null);
                }}
                helperText="Inclus dans le mix complet apres regeneration modem."
              />
            ) : null}

            {beepMode === "dtmf" ? (
              <Typography variant="body2" color="text.secondary">
                Tonalite DTMF generee par le modem - pas de fichier a choisir.
              </Typography>
            ) : null}

            {beepMode === "croche" ? (
              <VgBeepPatternEditor
                bpm={audio.record_beep_bpm ?? 100}
                gapMs={audio.record_beep_gap_ms ?? 45}
                notes={beepNotes}
                onBpmChange={(bpm) => {
                  patchAudio({ record_beep_bpm: bpm });
                  setBeepPresetId(null);
                }}
                onGapMsChange={(gapMs) => {
                  patchAudio({ record_beep_gap_ms: gapMs });
                  setBeepPresetId(null);
                }}
                onNotesChange={(notes) => {
                  patchAudio({ record_beep_notes: notes });
                  setBeepPresetId(null);
                }}
                audioPatch={{
                  record_beep: "croche",
                  record_beep_bpm: audio.record_beep_bpm ?? 100,
                  record_beep_gap_ms: audio.record_beep_gap_ms ?? 45,
                  record_beep_notes: beepNotes
                }}
              />
            ) : null}

            {beepMode === "none" ? (
              <Typography variant="body2" color="text.secondary">
                Aucun signal : l&apos;enregistrement demarre directement apres le message
                d&apos;accueil.
              </Typography>
            ) : null}
          </VgCollapsibleAudioSection>

          <VgCollapsibleAudioSection
            title="Appel bloque"
            description="Message joue quand un numero commercial / blacklist est refuse."
            icon={<BlockIcon color="error" fontSize="small" />}
            summary={audio.blocked_source === "tts" ? "TTS" : "WAV"}
          >
            <VgAudioPresetChips
              title="Prereglage bloque"
              presets={blockedPresets}
              loading={presetsLoading}
              activePresetId={blockedPresetId}
              onApply={(preset) => applyAudioPreset(preset, "blocked")}
            />
            <VgAudioSourcePicker
              label="Message bloque"
              source={audio.blocked_source || "wav"}
              onSourceChange={(v) => {
                patchAudio({ blocked_source: v });
                setBlockedPresetId(null);
              }}
              wavPath={audio.blocked_wav_path || "resources/voice/system/blocked_short.wav"}
              onWavPathChange={(v) => {
                patchAudio({ blocked_wav_path: v || null });
                setBlockedPresetId(null);
              }}
              ttsText={audio.blocked_tts_text || ""}
              onTtsTextChange={(v) => {
                patchAudio({ blocked_tts_text: v || null });
                setBlockedPresetId(null);
              }}
              ttsMultiline={false}
            />
          </VgCollapsibleAudioSection>

          <VgSaveBar
            autoSave
            saving={saving}
            dirty={dirty}
            error={error}
            success={success}
            onSave={() => void save()}
            onDismissError={() => setError(null)}
            onDismissSuccess={() => setSuccess(null)}
          />
        </Stack>
      ) : null}
    </AppLayout>
  );
}
