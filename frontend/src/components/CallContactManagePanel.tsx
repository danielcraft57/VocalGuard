"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Alert,
  Box,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography
} from "@mui/material";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import {
  addToBlocklist,
  addToWhitelist,
  createCallerRecord,
  fetchCallerByPhone,
  updateCaller,
  type Caller
} from "../services/callersFilterApi";
import { createClient } from "../services/clientsApi";

export type CallFilterChoice = "whitelist" | "screened" | "blocklist";

const DEFAULT_GREETING =
  "Bonjour {name}, ravi de vous entendre. Laissez votre message apres le bip, je vous rappelle des que possible.";

type Props = {
  phoneNumber: string;
  initialName?: string | null;
};

/**
 * Formulaire contact + filtrage + accueil perso depuis la fiche appel.
 */
export function CallContactManagePanel({ phoneNumber, initialName }: Props): React.ReactElement | null {
  const phone = phoneNumber.trim();
  const [caller, setCaller] = useState<Caller | null>(null);
  const [displayName, setDisplayName] = useState(initialName?.trim() || "");
  const [filter, setFilter] = useState<CallFilterChoice>("screened");
  const [greeting, setGreeting] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    setDisplayName(initialName?.trim() || caller?.name?.trim() || "");
  }, [initialName, caller?.name]);

  useEffect(() => {
    if (!phone) return undefined;
    const ac = new AbortController();
    setLoading(true);
    setError(null);
    void fetchCallerByPhone(phone, ac.signal)
      .then((row) => {
        setCaller(row);
        if (row?.name) setDisplayName(row.name);
        if (row?.greeting_tts_text) setGreeting(row.greeting_tts_text);
        if (row?.is_whitelisted) setFilter("whitelist");
        else if (row?.is_blocked) setFilter("blocklist");
        else setFilter("screened");
      })
      .catch((e: unknown) => {
        if (ac.signal.aborted) return;
        setError(e instanceof Error ? e.message : "Impossible de charger le filtrage");
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [phone]);

  const onSave = useCallback(async () => {
    if (!phone) return;
    const name = displayName.trim();
    if (!name) {
      setError("Donne un nom pour ce contact.");
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await createClient({ phone_number: phone, name }).catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : "";
        if (msg.includes("409") || msg.toLowerCase().includes("existe")) return;
        throw e;
      });

      const greetingText =
        filter === "whitelist" ? (greeting.trim() || DEFAULT_GREETING) : null;

      let saved: Caller;
      if (filter === "whitelist") {
        saved = await addToWhitelist(phone, name, null, greetingText);
      } else if (filter === "blocklist") {
        saved = await addToBlocklist(phone, name, null);
        if (greetingText) {
          saved = await updateCaller(saved.id, { greeting_tts_text: null });
        }
      } else {
        if (caller?.id) {
          saved = await updateCaller(caller.id, {
            name,
            is_whitelisted: false,
            is_blocked: false,
            greeting_tts_text: null
          });
        } else {
          try {
            saved = await createCallerRecord({
              phone_number: phone,
              name,
              is_whitelisted: false,
              is_blocked: false,
              greeting_tts_text: null
            });
          } catch (e: unknown) {
            const again = await fetchCallerByPhone(phone);
            if (!again?.id) throw e;
            saved = await updateCaller(again.id, {
              name,
              is_whitelisted: false,
              is_blocked: false,
              greeting_tts_text: null
            });
          }
        }
      }

      setCaller(saved);
      setSuccess("Contact et filtrage enregistres.");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur lors de l'enregistrement");
    } finally {
      setSaving(false);
    }
  }, [caller?.id, displayName, filter, greeting, phone]);

  if (!phone) return null;

  return (
    <Box
      sx={{
        mx: { xs: 2, sm: 3 },
        mt: 2,
        p: 2,
        borderRadius: 2,
        border: "1px solid",
        borderColor: "divider"
      }}
    >
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
        <PersonAddIcon fontSize="small" color="primary" />
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: "0.12em" }}>
          Contact et filtrage
        </Typography>
      </Stack>

      {loading ? (
        <Typography variant="body2" color="text.secondary">
          Chargement du filtrage…
        </Typography>
      ) : (
        <Stack spacing={1.5}>
          <TextField
            size="small"
            label="Nom du contact"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            fullWidth
          />
          <FormControl size="small" fullWidth>
            <InputLabel id="vg-call-filter-label">Filtrage</InputLabel>
            <Select
              labelId="vg-call-filter-label"
              label="Filtrage"
              value={filter}
              onChange={(e) => setFilter(e.target.value as CallFilterChoice)}
            >
              <MenuItem value="whitelist">Autorise (liste blanche)</MenuItem>
              <MenuItem value="screened">Filtre (inconnu / repondeur)</MenuItem>
              <MenuItem value="blocklist">Bloque</MenuItem>
            </Select>
          </FormControl>
          {filter === "whitelist" ? (
            <TextField
              size="small"
              label="Message d'accueil"
              value={greeting}
              placeholder={DEFAULT_GREETING}
              onChange={(e) => setGreeting(e.target.value)}
              multiline
              minRows={3}
              fullWidth
              helperText="Utilise {name} pour le prenom ou le nom saisi ci-dessus."
            />
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {success ? <Alert severity="success">{success}</Alert> : null}
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Button variant="contained" disabled={saving} onClick={() => void onSave()}>
              {saving ? "Enregistrement…" : "Enregistrer le contact"}
            </Button>
            <Button component={Link} href="/filtering" size="small" color="inherit">
              Voir tout le filtrage
            </Button>
          </Stack>
        </Stack>
      )}
    </Box>
  );
}
