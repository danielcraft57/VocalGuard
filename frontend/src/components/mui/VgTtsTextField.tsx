"use client";

import React, { useCallback, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Chip,
  Collapse,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import PauseIcon from "@mui/icons-material/Pause";
import TextFieldsIcon from "@mui/icons-material/TextFields";

/** Insertion de ponctuation ou balise experimentale dans le texte TTS. */
type TtsInsertPreset = {
  id: string;
  label: string;
  tooltip: string;
  snippet: string;
  icon: React.ReactNode;
  experimental?: boolean;
};

/** Inserts fiables : ponctuation naturelle (recommande pour le modem). */
const TTS_INSERT_PRESETS: TtsInsertPreset[] = [
  {
    id: "comma",
    label: "Virgule",
    tooltip: "Micro-pause naturelle (recommande)",
    snippet: ", ",
    icon: <PauseIcon sx={{ fontSize: 16 }} />
  },
  {
    id: "dot",
    label: "Point",
    tooltip: "Fin de phrase + pause",
    snippet: ". ",
    icon: <TextFieldsIcon sx={{ fontSize: 16 }} />
  },
  {
    id: "ellipsis",
    label: "Suspension",
    tooltip: "Pause un peu plus longue (...)",
    snippet: "... ",
    icon: <MoreHorizIcon sx={{ fontSize: 16 }} />
  }
];

/** Balises SSML : support Edge TTS limite, peut etre lu a voix haute. */
const TTS_EXPERIMENTAL_PRESETS: TtsInsertPreset[] = [
  {
    id: "break_short",
    label: "SSML pause",
    tooltip: "Experimental — peut ne pas fonctionner (lu a voix haute)",
    snippet: '<break time="400ms"/>',
    icon: <PauseIcon sx={{ fontSize: 16 }} />,
    experimental: true
  }
];

const MAX_TTS_CHARS = 600;

export type VgTtsTextFieldProps = {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  minRows?: number;
};

/**
 * Insere un fragment au curseur.
 *
 * @param text Texte courant.
 * @param start Index debut selection.
 * @param end Index fin selection.
 * @param snippet Fragment a inserer.
 * @returns Nouveau texte et position curseur.
 */
function insertAtCursor(
  text: string,
  start: number,
  end: number,
  snippet: string
): { next: string; cursor: number } {
  const next = text.slice(0, start) + snippet + text.slice(end);
  return { next, cursor: start + snippet.length };
}

/**
 * Champ texte TTS Material Design avec barre d'outils ponctuation + aide Edge TTS.
 */
export function VgTtsTextField({
  label = "Texte TTS",
  value,
  onChange,
  placeholder,
  disabled = false,
  minRows = 4
}: VgTtsTextFieldProps) {
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const hasExperimentalSsml = useMemo(() => /<break\b|<emphasis\b|<prosody\b/i.test(value), [value]);

  const handleInsert = useCallback(
    (snippet: string) => {
      const el = inputRef.current;
      const start = el?.selectionStart ?? value.length;
      const end = el?.selectionEnd ?? value.length;
      const { next, cursor } = insertAtCursor(value, start, end, snippet);
      if (next.length > MAX_TTS_CHARS) return;
      onChange(next);
      requestAnimationFrame(() => {
        if (!el) return;
        el.focus();
        el.setSelectionRange(cursor, cursor);
      });
    },
    [onChange, value]
  );

  const renderChip = (preset: TtsInsertPreset) => (
    <Tooltip key={preset.id} title={preset.tooltip} arrow>
      <Chip
        size="small"
        icon={preset.icon as React.ReactElement}
        label={preset.label}
        onClick={() => handleInsert(preset.snippet)}
        disabled={disabled}
        variant={preset.experimental ? "outlined" : "filled"}
        color={preset.experimental ? "warning" : "default"}
        sx={{
          borderRadius: 1.5,
          "& .MuiChip-icon": { ml: 0.5 }
        }}
      />
    </Tooltip>
  );

  return (
    <Stack spacing={1}>
      {label ? (
        <Typography variant="subtitle2" color="text.secondary">
          {label}
        </Typography>
      ) : null}

      <Box
        sx={{
          border: 1,
          borderColor: hasExperimentalSsml ? "warning.main" : "divider",
          borderRadius: 2,
          overflow: "hidden",
          bgcolor: "background.paper",
          transition: "border-color 0.2s"
        }}
      >
        <Stack
          direction="row"
          spacing={0.5}
          useFlexGap
          sx={{
            alignItems: "center",
            flexWrap: "wrap",
            px: 1.25,
            py: 0.75,
            borderBottom: 1,
            borderColor: "divider",
            bgcolor: (theme) =>
              theme.palette.mode === "dark" ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.02)"
          }}
        >
          <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
            Rythme
          </Typography>
          {TTS_INSERT_PRESETS.map(renderChip)}
          <Chip
            size="small"
            label={advancedOpen ? "Masquer SSML" : "SSML ?"}
            variant="outlined"
            color="warning"
            onClick={() => setAdvancedOpen((v) => !v)}
            sx={{ borderRadius: 1.5 }}
          />
          <Box sx={{ flexGrow: 1 }} />
          <Tooltip title="Ce qui marche avec Edge TTS">
            <IconButton
              size="small"
              onClick={() => setHelpOpen((v) => !v)}
              color={helpOpen ? "primary" : "default"}
              aria-label="Aide TTS"
            >
              <InfoOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>

        <Collapse in={advancedOpen}>
          <Stack
            direction="row"
            spacing={0.5}
            useFlexGap
            sx={{
              alignItems: "center",
              flexWrap: "wrap",
              px: 1.25,
              py: 0.75,
              borderBottom: 1,
              borderColor: "divider"
            }}
          >
            <Typography variant="caption" color="warning.main">
              Experimental
            </Typography>
            {TTS_EXPERIMENTAL_PRESETS.map(renderChip)}
          </Stack>
        </Collapse>

        <TextField
          inputRef={inputRef}
          multiline
          minRows={minRows}
          fullWidth
          variant="standard"
          value={value}
          onChange={(e) => onChange(e.target.value.slice(0, MAX_TTS_CHARS))}
          placeholder={placeholder}
          disabled={disabled}
          slotProps={{
            input: {
              disableUnderline: true,
              sx: {
                px: 2,
                py: 1.5,
                fontSize: "0.95rem",
                lineHeight: 1.65,
                fontFamily: hasExperimentalSsml
                  ? '"Roboto Mono", "Consolas", monospace'
                  : "inherit"
              }
            },
            htmlInput: {
              maxLength: MAX_TTS_CHARS,
              "aria-label": label
            }
          }}
        />

        <Stack
          direction="row"
          sx={{
            alignItems: "center",
            justifyContent: "space-between",
            px: 1.5,
            py: 0.75,
            borderTop: 1,
            borderColor: "divider",
            gap: 1,
            flexWrap: "wrap"
          }}
        >
          <Typography variant="caption" color="text.secondary">
            {hasExperimentalSsml
              ? "SSML detecte — resultat non garanti sur le modem"
              : "Debit et hauteur : reglages au-dessus (pas dans le texte)"}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {value.length}/{MAX_TTS_CHARS}
          </Typography>
        </Stack>
      </Box>

      <Collapse in={helpOpen}>
        <Alert severity="info" sx={{ py: 0.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
            Edge TTS : peu de balises inline
          </Typography>
          <Typography variant="caption" component="div" color="text.secondary">
            Microsoft limite le SSML custom. Sur VocalGuard, ce qui marche vraiment :
          </Typography>
          <Box
            component="ul"
            sx={{
              m: 0.5,
              pl: 2.5,
              "& li": { typography: "caption", color: "text.secondary", mb: 0.25 }
            }}
          >
            <li>
              <strong>Voix</strong>, <strong>debit</strong> et <strong>hauteur</strong> (sliders
              au-dessus) — sur tout le message
            </li>
            <li>
              <strong>Ponctuation</strong> : virgules, points, <code>...</code> — le plus fiable
              pour le rythme
            </li>
            <li>
              Intro musicale, mix et normalisation modem (section plus bas)
            </li>
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
            Balises SSML classiques (<code>prosody</code>, <code>say-as</code>,{" "}
            <code>phoneme</code>, <code>emphasis</code>…) : en general ignorees ou lues a voix haute.
            On a deja eu un accueil de 27 s a cause de ca.
          </Typography>
        </Alert>
      </Collapse>
    </Stack>
  );
}
