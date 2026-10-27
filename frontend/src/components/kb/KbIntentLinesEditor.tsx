"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  IconButton,
  Stack,
  TextField,
  Typography
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";

/** Une ligne editable avec id stable (evite le bug React index). */
export type KbLineItem = {
  id: string;
  text: string;
};

export type KbIntentLinesEditorProps = {
  /** Titre de section. */
  title: string;
  /** Sous-titre court. */
  hint?: string;
  /** Lignes editees (ids stables). */
  items: KbLineItem[];
  /** Remplacement de la liste. */
  onChange: (items: KbLineItem[]) => void;
  /** Placeholder d'une ligne vide. */
  placeholder?: string;
  /** Mode compact (patterns) vs zone texte (reponses). */
  dense?: boolean;
  /** Affiche badge "voix" sur la 1ere ligne. */
  markFirstAsVoice?: boolean;
  /** Bouton ecoute TTS sur chaque ligne (reponses). */
  onPlay?: (item: KbLineItem, index: number) => void | Promise<void>;
  /** Id de la ligne en cours de generation audio. */
  playingId?: string | null;
};

/**
 * Cree un id unique pour une ligne.
 *
 * @returns Id.
 */
export function newLineId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `line_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * Convertit des strings en items a id stable.
 *
 * @param lines Textes.
 * @returns Items.
 */
export function linesToItems(lines: string[]): KbLineItem[] {
  const cleaned = lines.length ? lines : [""];
  return cleaned.map((text) => ({ id: newLineId(), text }));
}

/**
 * Extraire les textes (trim, drop vide).
 *
 * @param items Items.
 * @returns Textes utiles.
 */
export function itemsToCleanLines(items: KbLineItem[]): string[] {
  return items.map((i) => i.text.trim()).filter(Boolean);
}

/**
 * Editeur de lignes a id stable : liste verticale, une carte = une entree.
 *
 * Evite le bug ou editer une ligne reecrit toutes les autres (keys index).
 */
export function KbIntentLinesEditor({
  title,
  hint,
  items,
  onChange,
  placeholder = "Nouvelle ligne…",
  dense = false,
  markFirstAsVoice = false,
  onPlay,
  playingId = null
}: KbIntentLinesEditorProps): React.ReactElement {
  const updateAt = useCallback(
    (id: string, value: string) => {
      onChange(items.map((it) => (it.id === id ? { ...it, text: value } : it)));
    },
    [items, onChange]
  );

  const removeAt = useCallback(
    (id: string) => {
      const next = items.filter((it) => it.id !== id);
      onChange(next.length ? next : [{ id: newLineId(), text: "" }]);
    },
    [items, onChange]
  );

  const move = useCallback(
    (id: string, dir: -1 | 1) => {
      const index = items.findIndex((it) => it.id === id);
      if (index < 0) return;
      const j = index + dir;
      if (j < 0 || j >= items.length) return;
      const next = items.slice();
      const tmp = next[index];
      next[index] = next[j];
      next[j] = tmp;
      onChange(next);
    },
    [items, onChange]
  );

  const addLine = useCallback(() => {
    onChange([...items, { id: newLineId(), text: "" }]);
  }, [items, onChange]);

  return (
    <Stack spacing={1}>
      <Stack
        direction="row"
        spacing={1}
        sx={{ alignItems: "center", justifyContent: "space-between" }}
      >
        <Box>
          <Typography variant="subtitle2">
            {title}{" "}
            <Typography component="span" variant="caption" color="text.secondary">
              ({items.length})
            </Typography>
          </Typography>
          {hint ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              {hint}
            </Typography>
          ) : null}
        </Box>
        <Button size="small" startIcon={<AddIcon />} onClick={addLine} variant="outlined">
          Ajouter
        </Button>
      </Stack>

      <Stack spacing={1}>
        {items.map((item, index) => (
          <Box
            key={item.id}
            sx={{
              p: dense ? 0.75 : 1,
              borderRadius: 1.25,
              border: "1px solid",
              borderColor: "divider",
              bgcolor: "background.paper"
            }}
          >
            <Stack direction="row" spacing={0.5} sx={{ alignItems: "flex-start", gap: 0.5 }}>
              <Stack spacing={0.25} sx={{ pt: 0.5, minWidth: 28, alignItems: "center" }}>
                {markFirstAsVoice && index === 0 ? (
                  <Chip size="small" color="primary" label="Voix" sx={{ height: 22 }} />
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    {index + 1}
                  </Typography>
                )}
              </Stack>

              <TextField
                size="small"
                fullWidth
                multiline={!dense}
                minRows={dense ? 1 : 2}
                maxRows={dense ? 3 : 8}
                placeholder={placeholder}
                value={item.text}
                onChange={(e) => updateAt(item.id, e.target.value)}
                sx={{ flex: 1 }}
              />

              <Stack direction="row" spacing={0} sx={{ flexShrink: 0, pt: 0.25 }}>
                {onPlay ? (
                  <IconButton
                    size="small"
                    aria-label="ecouter"
                    color="primary"
                    disabled={!item.text.trim() || playingId === item.id}
                    onClick={() => void onPlay(item, index)}
                  >
                    {playingId === item.id ? (
                      <CircularProgress size={16} />
                    ) : (
                      <PlayArrowIcon fontSize="small" />
                    )}
                  </IconButton>
                ) : null}
                <IconButton
                  size="small"
                  aria-label="monter"
                  disabled={index === 0}
                  onClick={() => move(item.id, -1)}
                >
                  <ArrowUpwardIcon fontSize="inherit" />
                </IconButton>
                <IconButton
                  size="small"
                  aria-label="descendre"
                  disabled={index === items.length - 1}
                  onClick={() => move(item.id, 1)}
                >
                  <ArrowDownwardIcon fontSize="inherit" />
                </IconButton>
                <IconButton
                  size="small"
                  aria-label="supprimer"
                  color="error"
                  onClick={() => removeAt(item.id)}
                >
                  <DeleteIcon fontSize="inherit" />
                </IconButton>
              </Stack>
            </Stack>
          </Box>
        ))}
      </Stack>
    </Stack>
  );
}

/**
 * Debounce simple pour autosave.
 *
 * @param value Valeur.
 * @param ms Delai.
 * @returns Valeur debounced.
 */
export function useDebouncedValue<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      setDebounced(value);
      return;
    }
    const t = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return debounced;
}
