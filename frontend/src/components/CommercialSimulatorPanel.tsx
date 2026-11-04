/**
 * Simulateur commercial sortant : texte prospect → QCM → lecture HP.
 */

"use client";

import React, { useCallback, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Paper,
  Stack,
  TextField,
  Typography
} from "@mui/material";
import CampaignIcon from "@mui/icons-material/Campaign";
import VolumeUpIcon from "@mui/icons-material/VolumeUp";
import { OutboundCommercialChoicesPanel } from "./OutboundCommercialChoicesPanel";
import {
  suggestCommercial,
  type CommercialSuggestion
} from "../services/outboundCommercialApi";
import { isAbortError } from "../services/uiPersist";

/**
 * Boucle texte → suggest → choix 1-5 → WAV sur haut-parleurs.
 *
 * @returns Panneau Material.
 */
export function CommercialSimulatorPanel(): React.ReactElement {
  const [text, setText] = useState("");
  const [suggestions, setSuggestions] = useState<CommercialSuggestion[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [engine, setEngine] = useState<string | null>(null);

  const runSuggest = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      const res = await suggestCommercial(trimmed);
      setSuggestions(res.suggestions || []);
      setEngine(res.engine || null);
      if (!(res.suggestions || []).length) {
        setError("Aucune situation trouvee pour ce texte.");
      }
    } catch (e) {
      if (isAbortError(e)) return;
      setError(e instanceof Error ? e.message : "Suggest impossible");
      setSuggestions([]);
    } finally {
      setBusy(false);
    }
  }, [text]);

  return (
    <Stack spacing={2}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
          <CampaignIcon color="primary" />
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            Prospect (texte)
          </Typography>
          {engine ? (
            <Typography variant="caption" color="text.secondary">
              moteur {engine}
            </Typography>
          ) : null}
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          Tape ce que dirait le prospect. Marie enquiquine un peu et propose un
          mini-jeu de questions. Puis choisis situation et phrase (1-5) pour
          entendre la voix sur les HP.
        </Typography>
        <TextField
          label="Parole du prospect"
          placeholder="Ex. C'est trop cher, on a deja un prestataire…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          fullWidth
          multiline
          minRows={2}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void runSuggest();
            }
          }}
        />
        <Stack direction="row" spacing={1} sx={{ mt: 1.5, flexWrap: "wrap", gap: 1 }}>
          <Button
            variant="contained"
            disabled={busy || !text.trim()}
            onClick={() => void runSuggest()}
            startIcon={<VolumeUpIcon />}
          >
            Proposer 5 situations
          </Button>
          <Button
            variant="outlined"
            disabled={busy || suggestions.length === 0}
            onClick={() => {
              setSuggestions([]);
              setError(null);
            }}
          >
            Effacer
          </Button>
        </Stack>
        {error ? (
          <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        ) : null}
      </Paper>

      <Box
        sx={{
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 2,
          overflow: "hidden",
          bgcolor: "background.paper"
        }}
      >
        <OutboundCommercialChoicesPanel
          open
          callId={null}
          connected={false}
          suggestions={suggestions}
          playbackMode="speakers"
          emptyHint="Saisis un texte prospect ci-dessus, puis « Proposer 5 situations »."
          onClearSuggestions={() => {
            /* garde les suggestions pour enchainement, ou clear ? on laisse */
          }}
        />
      </Box>
    </Stack>
  );
}
