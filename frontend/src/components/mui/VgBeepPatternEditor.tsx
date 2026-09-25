"use client";

import React, { useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlinedIcon from "@mui/icons-material/DeleteOutlined";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import StopIcon from "@mui/icons-material/Stop";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import GraphicEqIcon from "@mui/icons-material/GraphicEq";
import MusicNoteIcon from "@mui/icons-material/MusicNote";
import { previewBeepPattern } from "../../services/settingsApi";

export type BeepRhythm = "noire" | "croche" | "double_croche" | "triolet";

export type BeepNote = {
  pitch: string;
  rhythm: BeepRhythm;
};

export type VgBeepPatternEditorProps = {
  /** Tempo (battements noire / minute). */
  bpm: number;
  /** Silence entre notes (ms). */
  gapMs: number;
  /** Partition courante. */
  notes: BeepNote[];
  /** Mise a jour tempo. */
  onBpmChange: (bpm: number) => void;
  /** Mise a jour gap. */
  onGapMsChange: (gapMs: number) => void;
  /** Mise a jour partition. */
  onNotesChange: (notes: BeepNote[]) => void;
  /** Patch audio pour l'apercu API. */
  audioPatch?: Record<string, unknown>;
};

const PITCH_OPTIONS: { id: string; label: string }[] = [
  { id: "rest", label: "Silence" },
  { id: "C4", label: "Do4" },
  { id: "C#4", label: "Do#4" },
  { id: "D4", label: "Re4" },
  { id: "D#4", label: "Re#4" },
  { id: "E4", label: "Mi4" },
  { id: "F4", label: "Fa4" },
  { id: "F#4", label: "Fa#4" },
  { id: "G4", label: "Sol4" },
  { id: "G#4", label: "Sol#4" },
  { id: "A4", label: "La4" },
  { id: "A#4", label: "La#4" },
  { id: "B4", label: "Si4" },
  { id: "C5", label: "Do5" },
  { id: "C#5", label: "Do#5" },
  { id: "D5", label: "Re5" },
  { id: "D#5", label: "Re#5" },
  { id: "E5", label: "Mi5" },
  { id: "F5", label: "Fa5" },
  { id: "F#5", label: "Fa#5" },
  { id: "G5", label: "Sol5" },
  { id: "G#5", label: "Sol#5" },
  { id: "A5", label: "La5" },
  { id: "A#5", label: "La#5" },
  { id: "B5", label: "Si5" },
  { id: "C6", label: "Do6" }
];

const RHYTHM_OPTIONS: {
  id: BeepRhythm;
  label: string;
  short: string;
  symbol: string;
  hint: string;
  /** Largeur relative dans la timeline (noire = 12). */
  weight: number;
  /** Fraction d'une noire. */
  beatFraction: number;
}[] = [
  {
    id: "noire",
    label: "Noire",
    short: "N",
    symbol: "♩",
    hint: "1 temps",
    weight: 12,
    beatFraction: 1
  },
  {
    id: "croche",
    label: "Croche",
    short: "C",
    symbol: "♪",
    hint: "1/2 temps — 2 croches = 1 noire",
    weight: 6,
    beatFraction: 0.5
  },
  {
    id: "double_croche",
    label: "Double croche",
    short: "DC",
    symbol: "♬",
    hint: "1/4 temps — 4 doubles = 1 noire",
    weight: 3,
    beatFraction: 0.25
  },
  {
    id: "triolet",
    label: "Triolet",
    short: "T",
    symbol: "³♪",
    hint: "1/3 temps — 3 triolets = 1 noire",
    weight: 4,
    beatFraction: 1 / 3
  }
];

const DEFAULT_NOTE: BeepNote = { pitch: "G5", rhythm: "croche" };
const MAX_NOTES = 12;

/**
 * Libelle FR d'une hauteur.
 *
 * @param pitch Code technique (G5, rest…).
 * @returns Libelle affiche.
 */
function pitchLabel(pitch: string): string {
  return PITCH_OPTIONS.find((p) => p.id === pitch)?.label || pitch;
}

/**
 * Meta rythme.
 *
 * @param rhythm Identifiant rythme.
 * @returns Option ou fallback croche.
 */
function rhythmMeta(rhythm: BeepRhythm) {
  return RHYTHM_OPTIONS.find((r) => r.id === rhythm) || RHYTHM_OPTIONS[1];
}

/**
 * Duree d'une case rythmique en secondes (meme formule que le backend).
 *
 * @param rhythm Valeur rythmique.
 * @param bpm Tempo noire.
 * @returns Secondes.
 */
function rhythmDurationSec(rhythm: BeepRhythm, bpm: number): number {
  const beat = 60 / Math.max(40, bpm);
  return beat * rhythmMeta(rhythm).beatFraction;
}

/**
 * Editeur de partition pour le bip d'enregistrement.
 *
 * Applique vraiment le solfege : noire, croche (1/2), double croche (1/4),
 * triolet (1/3, 3 notes = 1 temps). Insere des groupes musicaux coherents.
 */
export function VgBeepPatternEditor({
  bpm,
  gapMs,
  notes,
  onBpmChange,
  onGapMsChange,
  onNotesChange,
  audioPatch
}: VgBeepPatternEditorProps): React.ReactElement {
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  const safeNotes = useMemo(
    () =>
      notes.length > 0
        ? notes
        : [{ ...DEFAULT_NOTE }, { pitch: "E5", rhythm: "croche" as BeepRhythm }],
    [notes]
  );

  const sharedRhythm = useMemo(() => {
    const first = safeNotes[0]?.rhythm;
    if (!first) return null;
    return safeNotes.every((n) => n.rhythm === first) ? first : null;
  }, [safeNotes]);

  const totalBeats = useMemo(
    () => safeNotes.reduce((acc, n) => acc + rhythmMeta(n.rhythm).beatFraction, 0),
    [safeNotes]
  );

  const summary = useMemo(
    () =>
      safeNotes
        .map((n) => {
          const meta = rhythmMeta(n.rhythm);
          return `${meta.symbol} ${pitchLabel(n.pitch)}`;
        })
        .join("  "),
    [safeNotes]
  );

  const stopPreview = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setPreviewing(false);
  };

  /**
   * Met a jour une note de la partition.
   *
   * @param index Index dans la liste.
   * @param patch Champs a modifier.
   */
  const updateNote = (index: number, patch: Partial<BeepNote>) => {
    const next = safeNotes.map((n, i) => (i === index ? { ...n, ...patch } : n));
    onNotesChange(next);
  };

  /**
   * Deplace une note dans la partition.
   *
   * @param index Index courant.
   * @param delta -1 ou +1.
   */
  const moveNote = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= safeNotes.length) return;
    const next = [...safeNotes];
    const tmp = next[index];
    next[index] = next[target];
    next[target] = tmp;
    onNotesChange(next);
  };

  /**
   * Supprime une note (garde au moins une).
   *
   * @param index Index a retirer.
   */
  const removeNote = (index: number) => {
    if (safeNotes.length <= 1) return;
    onNotesChange(safeNotes.filter((_, i) => i !== index));
  };

  /**
   * Applique le meme rythme a toutes les notes.
   *
   * @param rhythm Rythme cible.
   */
  const applyRhythmToAll = (rhythm: BeepRhythm) => {
    onNotesChange(safeNotes.map((n) => ({ ...n, rhythm })));
  };

  /**
   * Ajoute une note avec un rythme donne.
   *
   * @param rhythm Valeur rythmique.
   * @param count Nombre de notes a empiler (3 pour un triolet complet).
   */
  const addRhythmNotes = (rhythm: BeepRhythm, count = 1) => {
    const room = MAX_NOTES - safeNotes.length;
    if (room <= 0) return;
    const last = safeNotes[safeNotes.length - 1] || DEFAULT_NOTE;
    const toAdd = Math.min(count, room);
    const pitches =
      rhythm === "triolet" && count === 3
        ? [last.pitch === "rest" ? "C5" : last.pitch, "E5", "G5"]
        : Array.from({ length: toAdd }, () => last.pitch);
    onNotesChange([
      ...safeNotes,
      ...pitches.slice(0, toAdd).map((pitch) => ({ pitch, rhythm }))
    ]);
  };

  /** Genere et joue l'apercu WAV du bip. */
  const handlePreview = async () => {
    setPreviewError(null);
    stopPreview();
    setPreviewing(true);
    try {
      const blob = await previewBeepPattern({
        ...(audioPatch || {}),
        record_beep: "croche",
        record_beep_bpm: bpm,
        record_beep_gap_ms: gapMs,
        record_beep_notes: safeNotes
      });
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      const el = new Audio(url);
      audioRef.current = el;
      el.onended = () => stopPreview();
      el.onerror = () => {
        setPreviewError("Lecture impossible");
        stopPreview();
      };
      await el.play();
    } catch (e) {
      setPreviewError(e instanceof Error ? e.message : "Apercu bip impossible");
      stopPreview();
    }
  };

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", md: "1.35fr 1fr" },
        gap: 2.5,
        alignItems: "start"
      }}
    >
      <Stack spacing={2}>
        <Stack spacing={0.5}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            Partition du bip
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Solfege reel : 1 noire = 2 croches = 4 doubles croches = 3 triolets.
            Chaque valeur change la duree du son (pas juste le libelle).
          </Typography>
        </Stack>

        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
            gap: 2
          }}
        >
          <Stack spacing={1}>
            <Typography variant="caption" color="text.secondary">
              Tempo : {bpm} BPM (noire = {(60 / bpm).toFixed(2)} s)
            </Typography>
            <Slider
              size="small"
              value={bpm}
              min={60}
              max={180}
              step={5}
              valueLabelDisplay="auto"
              onChange={(_, v) => onBpmChange(v as number)}
            />
          </Stack>
          <Stack spacing={1}>
            <Typography variant="caption" color="text.secondary">
              Articulation extra : {gapMs} ms
            </Typography>
            <Slider
              size="small"
              value={gapMs}
              min={0}
              max={120}
              step={5}
              valueLabelDisplay="auto"
              onChange={(_, v) => onGapMsChange(v as number)}
            />
          </Stack>
        </Box>

        <Stack spacing={0.75}>
          <Typography variant="caption" color="text.secondary">
            Ajouter (applique la vraie duree)
          </Typography>
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
            <Button
              size="small"
              variant="outlined"
              startIcon={<AddIcon />}
              disabled={safeNotes.length >= MAX_NOTES}
              onClick={() => addRhythmNotes("croche", 1)}
              sx={{ textTransform: "none", fontWeight: 600 }}
            >
              ♪ Croche
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<AddIcon />}
              disabled={safeNotes.length >= MAX_NOTES}
              onClick={() => addRhythmNotes("double_croche", 1)}
              sx={{ textTransform: "none", fontWeight: 600 }}
            >
              ♬ Double croche
            </Button>
            <Button
              size="small"
              variant="contained"
              color="warning"
              startIcon={<AddIcon />}
              disabled={safeNotes.length + 3 > MAX_NOTES}
              onClick={() => addRhythmNotes("triolet", 3)}
              sx={{ textTransform: "none", fontWeight: 600 }}
              title="3 notes egales qui tiennent dans 1 noire"
            >
              ³ Triolet (×3)
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<AddIcon />}
              disabled={safeNotes.length >= MAX_NOTES}
              onClick={() => addRhythmNotes("noire", 1)}
              sx={{ textTransform: "none", fontWeight: 600 }}
            >
              ♩ Noire
            </Button>
          </Stack>
        </Stack>

        <Stack spacing={0.75}>
          <Typography variant="caption" color="text.secondary">
            Appliquer un rythme a toute la partition
          </Typography>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={sharedRhythm}
            onChange={(_, value: BeepRhythm | null) => {
              if (value) applyRhythmToAll(value);
            }}
            aria-label="Rythme global"
            sx={{
              flexWrap: "wrap",
              "& .MuiToggleButton-root": {
                textTransform: "none",
                fontWeight: 600,
                px: 1.25
              }
            }}
          >
            {RHYTHM_OPTIONS.map((r) => (
              <ToggleButton key={r.id} value={r.id} aria-label={r.label} title={r.hint}>
                {r.symbol} {r.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Stack>

        <Stack spacing={1.25}>
          {safeNotes.map((note, index) => {
            const meta = rhythmMeta(note.rhythm);
            const durMs = Math.round(rhythmDurationSec(note.rhythm, bpm) * 1000);
            return (
              <Box
                key={`beep-note-${index}`}
                sx={{
                  p: 1.5,
                  border: 1,
                  borderColor: "divider",
                  borderRadius: 2,
                  bgcolor: "background.paper"
                }}
              >
                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={1}
                  sx={{ alignItems: { sm: "center" }, mb: 1 }}
                >
                  <Chip
                    size="small"
                    label={`${meta.symbol} #${index + 1}`}
                    color="warning"
                    variant="outlined"
                    sx={{ fontWeight: 700, alignSelf: "flex-start" }}
                  />
                  <FormControl size="small" sx={{ minWidth: 140, flex: 1 }}>
                    <InputLabel id={`beep-pitch-${index}`}>Note</InputLabel>
                    <Select
                      labelId={`beep-pitch-${index}`}
                      label="Note"
                      value={note.pitch}
                      onChange={(e) => updateNote(index, { pitch: e.target.value })}
                    >
                      {PITCH_OPTIONS.map((p) => (
                        <MenuItem key={p.id} value={p.id}>
                          {p.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ minWidth: 72, fontWeight: 600 }}
                  >
                    {durMs} ms
                  </Typography>
                  <Stack direction="row" spacing={0.25} sx={{ justifyContent: "flex-end" }}>
                    <IconButton
                      size="small"
                      aria-label="Monter"
                      disabled={index === 0}
                      onClick={() => moveNote(index, -1)}
                    >
                      <ArrowUpwardIcon fontSize="small" />
                    </IconButton>
                    <IconButton
                      size="small"
                      aria-label="Descendre"
                      disabled={index === safeNotes.length - 1}
                      onClick={() => moveNote(index, 1)}
                    >
                      <ArrowDownwardIcon fontSize="small" />
                    </IconButton>
                    <IconButton
                      size="small"
                      aria-label="Supprimer"
                      color="error"
                      disabled={safeNotes.length <= 1}
                      onClick={() => removeNote(index)}
                    >
                      <DeleteOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                </Stack>

                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                  Rythme — {meta.hint}
                </Typography>
                <ToggleButtonGroup
                  exclusive
                  fullWidth
                  size="small"
                  value={note.rhythm}
                  onChange={(_, value: BeepRhythm | null) => {
                    if (value) updateNote(index, { rhythm: value });
                  }}
                  aria-label={`Rythme note ${index + 1}`}
                  sx={{
                    flexWrap: { xs: "wrap", sm: "nowrap" },
                    "& .MuiToggleButton-root": {
                      textTransform: "none",
                      fontWeight: 600,
                      py: 0.85,
                      fontSize: "0.8rem"
                    }
                  }}
                >
                  {RHYTHM_OPTIONS.map((r) => (
                    <ToggleButton
                      key={r.id}
                      value={r.id}
                      color="warning"
                      aria-label={r.label}
                      title={r.hint}
                      sx={{ flex: 1, minWidth: { xs: "50%", sm: 0 } }}
                    >
                      {r.symbol} {r.label}
                    </ToggleButton>
                  ))}
                </ToggleButtonGroup>
              </Box>
            );
          })}
        </Stack>
      </Stack>

      <Box
        sx={{
          p: 2,
          borderRadius: 2,
          bgcolor: "action.hover",
          border: 1,
          borderColor: "divider",
          position: { md: "sticky" },
          top: { md: 16 }
        }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
          <GraphicEqIcon color="warning" fontSize="small" />
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            Apercu bip
          </Typography>
        </Stack>

        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          Timeline (largeur = duree reelle sur la grille)
        </Typography>
        <Box
          sx={{
            display: "flex",
            gap: 0.5,
            alignItems: "stretch",
            minHeight: 56,
            mb: 2,
            p: 1,
            borderRadius: 1.5,
            bgcolor: "background.paper",
            border: 1,
            borderColor: "divider",
            overflowX: "auto"
          }}
        >
          {safeNotes.map((note, index) => {
            const isRest = note.pitch === "rest";
            const meta = rhythmMeta(note.rhythm);
            return (
              <Tooltip
                key={`tl-${index}`}
                title={`${pitchLabel(note.pitch)} · ${meta.label} · ${Math.round(
                  rhythmDurationSec(note.rhythm, bpm) * 1000
                )} ms`}
              >
                <Box
                  sx={{
                    flex: `${meta.weight} 0 0`,
                    minWidth: 36,
                    borderRadius: 1,
                    px: 0.5,
                    py: 0.75,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    bgcolor: isRest ? "action.disabledBackground" : "warning.main",
                    color: isRest ? "text.secondary" : "warning.contrastText",
                    opacity: isRest ? 0.7 : 1
                  }}
                >
                  <Typography sx={{ fontSize: "1rem", lineHeight: 1, mb: 0.25 }}>
                    {meta.symbol}
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{ fontWeight: 700, lineHeight: 1.1, textAlign: "center" }}
                  >
                    {pitchLabel(note.pitch)}
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.9, fontSize: "0.65rem" }}>
                    {Math.round(rhythmDurationSec(note.rhythm, bpm) * 1000)}ms
                  </Typography>
                </Box>
              </Tooltip>
            );
          })}
        </Box>

        <Typography variant="body2" sx={{ mb: 0.5, fontWeight: 600 }}>
          {bpm} BPM · {totalBeats.toFixed(2)} temps · gap {gapMs} ms
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
          {summary}
        </Typography>

        <Stack spacing={1}>
          <Button
            fullWidth
            variant="contained"
            color="warning"
            startIcon={previewing ? <StopIcon /> : <PlayArrowIcon />}
            onClick={() => {
              if (previewing) stopPreview();
              else void handlePreview();
            }}
            sx={{ textTransform: "none", fontWeight: 600 }}
          >
            {previewing ? "Stop" : "Ecouter le bip"}
          </Button>
          <Button
            fullWidth
            variant="outlined"
            color="warning"
            startIcon={<MusicNoteIcon />}
            disabled={safeNotes.length + 3 > MAX_NOTES}
            onClick={() => {
              onNotesChange([
                { pitch: "C5", rhythm: "triolet" },
                { pitch: "E5", rhythm: "triolet" },
                { pitch: "G5", rhythm: "triolet" }
              ]);
            }}
            sx={{ textTransform: "none", fontWeight: 600 }}
          >
            Exemple : triolet Do-Mi-Sol
          </Button>
          <Button
            fullWidth
            variant="outlined"
            startIcon={<MusicNoteIcon />}
            onClick={() => {
              onNotesChange([
                { pitch: "A5", rhythm: "double_croche" },
                { pitch: "A5", rhythm: "double_croche" },
                { pitch: "A5", rhythm: "double_croche" },
                { pitch: "A5", rhythm: "double_croche" }
              ]);
            }}
            sx={{ textTransform: "none", fontWeight: 600 }}
          >
            Exemple : 4 doubles croches
          </Button>
        </Stack>

        {previewError ? (
          <Alert severity="error" sx={{ mt: 1.5, py: 0 }} onClose={() => setPreviewError(null)}>
            {previewError}
          </Alert>
        ) : (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
            A l&apos;ecoute, une croche doit durer ~2× une double croche ; un triolet ×3
            remplit exactement une noire.
          </Typography>
        )}
      </Box>
    </Box>
  );
}
