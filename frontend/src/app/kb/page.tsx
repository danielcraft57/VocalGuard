"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  InputAdornment,
  Stack,
  Switch,
  TextField,
  Typography
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import SearchIcon from "@mui/icons-material/Search";
import MicIcon from "@mui/icons-material/Mic";
import { AppLayout } from "../../components/AppLayout";
import { KbVectorEngineChip } from "../../components/kb/KbVectorEngineChip";
import { VgPageHeader } from "../../components/mui/VgPageHeader";
import { VgSettingsSection } from "../../components/mui/VgSettingsSection";
import {
  createKbIntent,
  deleteKbIntent,
  fetchKbIntents,
  getKbIntentVoiceUrl,
  isAbortError,
  patchKbIntent,
  regenerateKbVoices,
  type KbIntent
} from "../../services/kbApi";
import {
  isIntentsCacheFresh,
  loadIntentsCache,
  loadKbUiState,
  saveIntentsCache,
  saveKbUiState
} from "../../services/kbUiPersist";
import {
  groupIntents,
  INTENT_GROUPS,
  type IntentGroupId
} from "./intentGroups";
import { KbIntentsListSkeleton, KbSoftSyncBar } from "../../components/kb/KbSkeleton";
import { PageLoader } from "../../components/PageLoader";

type IntentForm = {
  tag: string;
  patternsText: string;
  responsesText: string;
  priority: string;
  action: string;
  enabled: boolean;
};

/**
 * Formulaire vide pour creer un intent.
 *
 * @returns Etat initial.
 */
function emptyForm(): IntentForm {
  return {
    tag: "",
    patternsText: "",
    responsesText: "",
    priority: "10",
    action: "",
    enabled: true
  };
}

/**
 * Remplit le formulaire depuis un intent existant.
 *
 * @param row Intent.
 * @returns Formulaire.
 */
function formFromIntent(row: KbIntent): IntentForm {
  return {
    tag: row.tag,
    patternsText: row.patterns.join("\n"),
    responsesText: row.responses.join("\n"),
    priority: String(row.priority),
    action: row.action || "",
    enabled: row.enabled
  };
}

/**
 * Decoupe un textarea multi-lignes en liste non vide.
 *
 * @param text Contenu.
 * @returns Lignes nettoyees.
 */
function linesOf(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
}

/**
 * Page Base de connaissances : intents groupes, voix, Qdrant.
 * Le tchatche / historique vit sur /simulator.
 */
export default function KnowledgeBasePage(): React.ReactElement {
  const [intents, setIntents] = useState<KbIntent[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [regenBusy, setRegenBusy] = useState(false);
  const [regenMsg, setRegenMsg] = useState<string | null>(null);

  const [filterQ, setFilterQ] = useState("");
  const [groupFilter, setGroupFilter] = useState<IntentGroupId | "all">("all");

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const loadAbortRef = useRef<AbortController | null>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTag, setEditTag] = useState<string | null>(null);
  const [form, setForm] = useState<IntentForm>(emptyForm());
  const [saving, setSaving] = useState(false);
  const [deleteTag, setDeleteTag] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const ui = loadKbUiState();
    setFilterQ(ui.filterQ);
    setGroupFilter((ui.groupFilter as IntentGroupId | "all") || "all");
    const cache = loadIntentsCache();
    if (cache?.intents?.length) {
      setIntents(cache.intents);
      setLoading(false);
    }
    setHydrated(true);
    return () => {
      loadAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    saveKbUiState({ filterQ, groupFilter });
  }, [filterQ, groupFilter, hydrated]);

  const playVoice = useCallback((tag: string) => {
    const url = getKbIntentVoiceUrl(tag);
    if (!audioRef.current) audioRef.current = new Audio();
    const el = audioRef.current;
    el.src = url;
    void el.play().catch(() => {
      setError(`Lecture impossible pour ${tag} (WAV manquant ?)`);
    });
  }, []);

  const load = useCallback(async (opts?: { soft?: boolean }) => {
    const hasData = intents.length > 0;
    const soft = Boolean(opts?.soft) && hasData;
    if (soft) setSyncing(true);
    else if (!hasData) setLoading(true);
    setError(null);

    loadAbortRef.current?.abort();
    const ac = new AbortController();
    loadAbortRef.current = ac;

    try {
      const rows = await fetchKbIntents(false, ac.signal);
      if (ac.signal.aborted) return;
      setIntents(rows);
      saveIntentsCache(rows);
    } catch (e) {
      if (isAbortError(e) || ac.signal.aborted) return;
      if (!hasData) {
        setError(e instanceof Error ? e.message : "Erreur chargement KB");
      }
    } finally {
      if (!ac.signal.aborted) {
        setLoading(false);
        setSyncing(false);
      }
    }
  }, [intents.length]);

  useEffect(() => {
    if (!hydrated) return;
    const cache = loadIntentsCache();
    if (cache?.intents?.length && isIntentsCacheFresh(cache)) {
      setLoading(false);
      return;
    }
    void load({ soft: Boolean(cache?.intents?.length) });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- apres hydrate
  }, [hydrated]);

  const grouped = useMemo(
    () => groupIntents(intents, filterQ, groupFilter),
    [intents, filterQ, groupFilter]
  );

  const openCreate = useCallback(() => {
    setEditTag(null);
    setForm(emptyForm());
    setDialogOpen(true);
  }, []);

  const openEdit = useCallback((row: KbIntent) => {
    setEditTag(row.tag);
    setForm(formFromIntent(row));
    setDialogOpen(true);
  }, []);

  const saveIntent = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      const patterns = linesOf(form.patternsText);
      const responses = linesOf(form.responsesText);
      const priority = Math.max(0, Math.min(100, parseInt(form.priority, 10) || 10));
      const action = form.action.trim() || null;
      if (editTag) {
        await patchKbIntent(editTag, {
          patterns,
          responses,
          priority,
          enabled: form.enabled,
          action: action || undefined,
          clear_action: !action
        });
      } else {
        const tag = form.tag.trim().toLowerCase();
        if (!tag) throw new Error("Le tag est obligatoire");
        if (!responses.length) throw new Error("Au moins une reponse");
        await createKbIntent({
          tag,
          patterns,
          responses,
          priority,
          enabled: form.enabled,
          action
        });
      }
      setDialogOpen(false);
      await load({ soft: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur sauvegarde");
    } finally {
      setSaving(false);
    }
  }, [editTag, form, load]);

  const confirmDelete = useCallback(async () => {
    if (!deleteTag) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteKbIntent(deleteTag);
      setDeleteTag(null);
      await load({ soft: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur suppression");
    } finally {
      setDeleting(false);
    }
  }, [deleteTag, load]);

  const runRegen = useCallback(async () => {
    setRegenBusy(true);
    setRegenMsg(null);
    try {
      const r = await regenerateKbVoices(true);
      setRegenMsg(`Voix: ${r.ok} ok, ${r.skipped} ignorees, ${r.failed} echecs`);
      await load({ soft: true });
    } catch (e) {
      setRegenMsg(e instanceof Error ? e.message : "Echec regen");
    } finally {
      setRegenBusy(false);
    }
  }, [load]);

  return (
    <AppLayout title="Base de connaissances" hidePageHeader>
      <VgPageHeader
        title="Base de connaissances"
        subtitle="Intents, Qdrant (node15), voix. Le tchatche est sur le simulateur."
        action={
          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1, alignItems: "center" }}>
            <KbVectorEngineChip />
            <Button
              component={Link}
              href="/simulator"
              size="small"
              variant="contained"
              startIcon={<MicIcon />}
            >
              Simulateur / Tchatche
            </Button>
            <Button
              component={Link}
              href="/settings/incoming-audio"
              size="small"
              variant="outlined"
            >
              Voix d&apos;accueil
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={() => void load({ soft: intents.length > 0 })}
              disabled={loading || syncing}
            >
              Actualiser
            </Button>
            <Button size="small" variant="outlined" startIcon={<AddIcon />} onClick={openCreate}>
              Nouvel intent
            </Button>
            <Button
              size="small"
              variant="contained"
              startIcon={<RecordVoiceOverIcon />}
              onClick={() => void runRegen()}
              disabled={regenBusy}
            >
              Regenerer les voix
            </Button>
          </Stack>
        }
      />

      {error ? (
        <Typography color="error" sx={{ mb: 2 }}>
          {error}
        </Typography>
      ) : null}
      {regenMsg ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {regenMsg}
        </Typography>
      ) : null}
      {syncing ? (
        <Box sx={{ mb: 2 }}>
          <KbSoftSyncBar label="Synchronisation des intents…" />
        </Box>
      ) : null}

      <VgSettingsSection
        title={`Intents (${intents.length})`}
        description="Filtres + groupes. Pour tester les reponses : Simulateur / Tchatche."
      >
        <Stack spacing={1.5} sx={{ mb: 2 }}>
          <TextField
            size="small"
            fullWidth
            placeholder="Filtrer (tag, pattern, reponse…)"
            value={filterQ}
            onChange={(e) => setFilterQ(e.target.value)}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                )
              }
            }}
          />
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: "wrap", gap: 0.75 }}>
            <Chip
              size="small"
              label="Tous"
              color={groupFilter === "all" ? "primary" : "default"}
              onClick={() => setGroupFilter("all")}
              variant={groupFilter === "all" ? "filled" : "outlined"}
            />
            {INTENT_GROUPS.map((g) => (
              <Chip
                key={g.id}
                size="small"
                label={g.label}
                color={groupFilter === g.id ? "primary" : "default"}
                onClick={() => setGroupFilter(g.id)}
                variant={groupFilter === g.id ? "filled" : "outlined"}
              />
            ))}
          </Stack>
        </Stack>

        {loading && !intents.length ? (
          <Box>
            <PageLoader variant="inline" label="Chargement des intents…" />
            <Box sx={{ mt: 2 }}>
              <KbIntentsListSkeleton />
            </Box>
          </Box>
        ) : (
          INTENT_GROUPS.map((g) => {
            const rows = grouped[g.id];
            if (!rows.length) return null;
            return (
              <Accordion
                key={g.id}
                defaultExpanded={g.id === "accueil" || groupFilter === g.id}
                disableGutters
                elevation={0}
                sx={{
                  border: 1,
                  borderColor: "divider",
                  borderRadius: 1,
                  mb: 1,
                  "&:before": { display: "none" }
                }}
              >
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Stack spacing={0.25}>
                    <Typography variant="subtitle2">
                      {g.label}{" "}
                      <Typography component="span" variant="caption" color="text.secondary">
                        ({rows.length})
                      </Typography>
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {g.hint}
                    </Typography>
                  </Stack>
                </AccordionSummary>
                <AccordionDetails sx={{ pt: 0 }}>
                  <Stack spacing={1}>
                    {rows.map((row) => (
                      <Box
                        key={row.tag}
                        sx={{
                          p: 1.25,
                          borderRadius: 1,
                          border: "1px solid",
                          borderColor: "divider",
                          bgcolor: "background.paper"
                        }}
                      >
                        <Stack
                          direction={{ xs: "column", sm: "row" }}
                          spacing={1}
                          sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
                        >
                          <Box sx={{ minWidth: 0, flex: 1 }}>
                            <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mb: 0.5 }}>
                              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                {row.tag}
                              </Typography>
                              {!row.enabled ? <Chip size="small" label="off" /> : null}
                              {row.action ? (
                                <Chip size="small" variant="outlined" label={row.action} />
                              ) : null}
                              <Chip size="small" variant="outlined" label={`prio ${row.priority}`} />
                            </Stack>
                            <Typography
                              variant="body2"
                              color="text.secondary"
                              noWrap
                              title={row.responses[0] || ""}
                            >
                              {row.responses[0] || "—"}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {row.patterns.length} patterns · {row.responses.length} reponse
                              {row.responses.length > 1 ? "s" : ""}
                            </Typography>
                          </Box>
                          <Stack direction="row" spacing={0.5} sx={{ flexShrink: 0 }}>
                            <Button
                              size="small"
                              startIcon={<PlayArrowIcon />}
                              disabled={!row.has_wav}
                              onClick={() => playVoice(row.tag)}
                            >
                              {row.has_wav ? "Ecouter" : "Absent"}
                            </Button>
                            <IconButton size="small" aria-label="modifier" onClick={() => openEdit(row)}>
                              <EditIcon fontSize="small" />
                            </IconButton>
                            <IconButton
                              size="small"
                              aria-label="supprimer"
                              color="error"
                              onClick={() => setDeleteTag(row.tag)}
                            >
                              <DeleteIcon fontSize="small" />
                            </IconButton>
                          </Stack>
                        </Stack>
                      </Box>
                    ))}
                  </Stack>
                </AccordionDetails>
              </Accordion>
            );
          })
        )}
      </VgSettingsSection>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editTag ? `Modifier ${editTag}` : "Nouvel intent"}</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
          {!editTag ? (
            <TextField
              label="Tag (ex. mon_intent)"
              size="small"
              value={form.tag}
              onChange={(e) => setForm((f) => ({ ...f, tag: e.target.value }))}
              helperText="Minuscules, chiffres, underscore. Unique."
            />
          ) : null}
          <TextField
            label="Priorite"
            size="small"
            type="number"
            value={form.priority}
            onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}
          />
          <TextField
            label="Action (optionnel)"
            size="small"
            value={form.action}
            onChange={(e) => setForm((f) => ({ ...f, action: e.target.value }))}
            helperText="ex. record_message, collect_coords, hangup_soft"
          />
          <TextField
            label="Patterns (un par ligne)"
            size="small"
            multiline
            minRows={4}
            value={form.patternsText}
            onChange={(e) => setForm((f) => ({ ...f, patternsText: e.target.value }))}
          />
          <TextField
            label="Reponses (une par ligne, 1ere = voix)"
            size="small"
            multiline
            minRows={3}
            value={form.responsesText}
            onChange={(e) => setForm((f) => ({ ...f, responsesText: e.target.value }))}
          />
          <FormControlLabel
            control={
              <Switch
                checked={form.enabled}
                onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
              />
            }
            label="Active"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Annuler</Button>
          <Button variant="contained" onClick={() => void saveIntent()} disabled={saving}>
            {saving ? "…" : "Enregistrer"}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(deleteTag)} onClose={() => setDeleteTag(null)}>
        <DialogTitle>Supprimer l&apos;intent ?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Tu vas supprimer <strong>{deleteTag}</strong> (patterns, reponses, embeddings). Pas de
            retour en arriere.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTag(null)}>Annuler</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => void confirmDelete()}
            disabled={deleting}
          >
            {deleting ? "…" : "Supprimer"}
          </Button>
        </DialogActions>
      </Dialog>
    </AppLayout>
  );
}
