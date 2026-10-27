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
  Tab,
  Tabs,
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
import { KbVoicePrefsPanel } from "../../components/kb/KbVoicePrefsPanel";
import { ElevenLabsKeysPanel } from "../../components/kb/ElevenLabsKeysPanel";
import { VgPageHeader } from "../../components/mui/VgPageHeader";
import { VgSettingsSection } from "../../components/mui/VgSettingsSection";
import {
  createKbIntent,
  deleteKbIntent,
  fetchKbIntents,
  getKbIntentVoiceUrl,
  isAbortError,
  patchKbIntent,
  previewKbVoice,
  regenerateKbVoices,
  type KbIntent
} from "../../services/kbApi";
import { fetchIncomingCallConfig, patchIncomingCallConfig } from "../../services/settingsApi";
import {
  isIntentsCacheFresh,
  loadIntentsCache,
  loadKbUiState,
  saveIntentsCache,
  saveKbUiState,
  voicePrefsForProfile,
  type KbProfile,
  type KbUiState,
  type KbVoicePrefs
} from "../../services/kbUiPersist";
import {
  defaultExpandedGroupId,
  groupIntents,
  groupsForProfile,
  type IntentGroupId
} from "./intentGroups";
import { KbIntentsListSkeleton, KbSoftSyncBar } from "../../components/kb/KbSkeleton";
import {
  itemsToCleanLines,
  KbIntentLinesEditor,
  linesToItems,
  useDebouncedValue,
  type KbLineItem
} from "../../components/kb/KbIntentLinesEditor";
import { PageLoader } from "../../components/PageLoader";

type IntentForm = {
  tag: string;
  patterns: KbLineItem[];
  responses: KbLineItem[];
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
    patterns: linesToItems([""]),
    responses: linesToItems([""]),
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
    patterns: linesToItems(row.patterns.length ? row.patterns : [""]),
    responses: linesToItems(row.responses.length ? row.responses : [""]),
    priority: String(row.priority),
    action: row.action || "",
    enabled: row.enabled
  };
}

/**
 * Page Base de connaissances : deux catalogues (entrant / commercial), CRUD, TTS.
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
  const [profile, setProfile] = useState<KbProfile>("inbound");
  const [voiceByProfile, setVoiceByProfile] = useState<
    Partial<Record<KbProfile, KbVoicePrefs>>
  >({});

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const loadAbortRef = useRef<AbortController | null>(null);
  const profileRef = useRef<KbProfile>(profile);
  profileRef.current = profile;

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTag, setEditTag] = useState<string | null>(null);
  const [form, setForm] = useState<IntentForm>(emptyForm());
  const [saving, setSaving] = useState(false);
  const [saveOk, setSaveOk] = useState(false);
  const [deleteTag, setDeleteTag] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [playingLineId, setPlayingLineId] = useState<string | null>(null);
  const [voiceSaveMsg, setVoiceSaveMsg] = useState<string | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const voiceDirtyRef = useRef(false);

  const voicePrefs = useMemo(
    () =>
      voicePrefsForProfile(
        { filterQ, groupFilter, profile, voiceByProfile } as KbUiState,
        profile
      ),
    [filterQ, groupFilter, profile, voiceByProfile]
  );

  const debouncedVoicePrefs = useDebouncedValue(voicePrefs, 800);

  const patchVoice = useCallback(
    (patch: Partial<KbVoicePrefs>) => {
      voiceDirtyRef.current = true;
      setVoiceByProfile((prev) => ({
        ...prev,
        [profile]: { ...voicePrefs, ...patch }
      }));
    },
    [profile, voicePrefs]
  );

  /** Autosave prefs voix → settings audio (apres modification user). */
  useEffect(() => {
    if (!hydrated || !voiceDirtyRef.current) return;
    let cancelled = false;
    void (async () => {
      try {
        await patchIncomingCallConfig({
          audio: {
            tts_provider: debouncedVoicePrefs.tts_provider,
            edge_tts_voice: debouncedVoicePrefs.edge_tts_voice,
            edge_tts_rate: debouncedVoicePrefs.edge_tts_rate,
            edge_tts_pitch: debouncedVoicePrefs.edge_tts_pitch,
            tts_voice_gain_db: debouncedVoicePrefs.tts_voice_gain_db,
            elevenlabs_voice_id: debouncedVoicePrefs.elevenlabs_voice_id
          }
        });
        if (!cancelled) setVoiceSaveMsg("Voix enregistree");
      } catch (e) {
        if (!cancelled) {
          setVoiceSaveMsg(
            e instanceof Error ? e.message : "Echec sauvegarde voix"
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [debouncedVoicePrefs, hydrated]);

  useEffect(() => {
    if (!voiceSaveMsg) return;
    const t = window.setTimeout(() => setVoiceSaveMsg(null), 2500);
    return () => window.clearTimeout(t);
  }, [voiceSaveMsg]);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    const ui = loadKbUiState();
    setFilterQ(ui.filterQ);
    setGroupFilter((ui.groupFilter as IntentGroupId | "all") || "all");
    setProfile(ui.profile);
    setVoiceByProfile(ui.voiceByProfile || {});
    const cache = loadIntentsCache(ui.profile);
    if (cache?.intents?.length) {
      setIntents(cache.intents);
      setLoading(false);
    }
    setHydrated(true);
    void (async () => {
      try {
        const cfg = await fetchIncomingCallConfig();
        const audio = (cfg.audio || {}) as Record<string, unknown>;
        const fromSettings: KbVoicePrefs = {
          tts_provider:
            audio.tts_provider === "elevenlabs" ? "elevenlabs" : "edge",
          edge_tts_voice: String(
            audio.edge_tts_voice || "fr-FR-VivienneMultilingualNeural"
          ),
          edge_tts_rate: String(audio.edge_tts_rate || "+0%"),
          edge_tts_pitch: String(audio.edge_tts_pitch || "+0Hz"),
          tts_voice_gain_db: Number(audio.tts_voice_gain_db ?? -6),
          elevenlabs_voice_id: String(
            audio.elevenlabs_voice_id || "JBFqnCBsd6RMkjVDRZzb"
          )
        };
        setVoiceByProfile((prev) => ({
          ...prev,
          [ui.profile]: { ...fromSettings, ...(prev[ui.profile] || {}) }
        }));
      } catch {
        /* garde session / defauts */
      }
    })();
    return () => {
      loadAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    saveKbUiState({ filterQ, groupFilter, profile, voiceByProfile });
  }, [filterQ, groupFilter, profile, voiceByProfile, hydrated]);

  const playVoice = useCallback((tag: string) => {
    const url = getKbIntentVoiceUrl(tag);
    if (!audioRef.current) audioRef.current = new Audio();
    const el = audioRef.current;
    el.src = url;
    void el.play().catch(() => {
      setError(`Lecture impossible pour ${tag} (WAV manquant ?)`);
    });
  }, []);

  const load = useCallback(
    async (opts?: { soft?: boolean; profile?: KbProfile }) => {
      const prof = opts?.profile ?? profileRef.current;
      const hasData = intents.length > 0 && profileRef.current === prof;
      const soft = Boolean(opts?.soft) && hasData;
      if (soft) setSyncing(true);
      else if (!hasData) setLoading(true);
      setError(null);

      loadAbortRef.current?.abort();
      const ac = new AbortController();
      loadAbortRef.current = ac;

      try {
        const rows = await fetchKbIntents(false, ac.signal, prof);
        if (ac.signal.aborted) return;
        if (profileRef.current !== prof) return;
        setIntents(rows);
        saveIntentsCache(prof, rows);
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
    },
    [intents.length]
  );

  useEffect(() => {
    if (!hydrated) return;
    const cache = loadIntentsCache(profile);
    if (cache?.intents?.length) {
      setIntents(cache.intents);
      setLoading(false);
      if (isIntentsCacheFresh(cache)) return;
      void load({ soft: true, profile });
      return;
    }
    setIntents([]);
    void load({ soft: false, profile });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload au changement de profil
  }, [hydrated, profile]);

  const profileGroups = useMemo(() => groupsForProfile(profile), [profile]);

  const grouped = useMemo(
    () => groupIntents(intents, filterQ, groupFilter, profile),
    [intents, filterQ, groupFilter, profile]
  );

  const expandedDefault = useMemo(() => defaultExpandedGroupId(profile), [profile]);

  useEffect(() => {
    // Reset filtre groupe si l'id n'existe plus sur ce profil
    const ids = new Set(profileGroups.map((g) => g.id));
    if (groupFilter !== "all" && !ids.has(groupFilter)) {
      setGroupFilter("all");
    }
  }, [profileGroups, groupFilter]);

  const openCreate = useCallback(() => {
    setEditTag(null);
    setForm(emptyForm());
    setSaveOk(false);
    setDialogOpen(true);
  }, []);

  const openEdit = useCallback((row: KbIntent) => {
    setEditTag(row.tag);
    setForm(formFromIntent(row));
    setSaveOk(false);
    setDialogOpen(true);
  }, []);

  const saveIntent = useCallback(async () => {
    setSaving(true);
    setSaveOk(false);
    setError(null);
    try {
      const patterns = itemsToCleanLines(form.patterns);
      const responses = itemsToCleanLines(form.responses);
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
          action,
          profile
        });
        setEditTag(tag);
      }
      await load({ soft: true, profile });
      setSaveOk(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur sauvegarde");
    } finally {
      setSaving(false);
    }
  }, [editTag, form, load, profile]);

  const playResponsePreview = useCallback(
    async (item: KbLineItem, index: number) => {
      const text = item.text.trim();
      if (!text) return;
      setPlayingLineId(item.id);
      setError(null);
      try {
        const { blob } = await previewKbVoice({
          text,
          tts_provider: voicePrefs.tts_provider,
          edge_tts_voice: voicePrefs.edge_tts_voice,
          edge_tts_rate: voicePrefs.edge_tts_rate,
          edge_tts_pitch: voicePrefs.edge_tts_pitch,
          tts_voice_gain_db: voicePrefs.tts_voice_gain_db,
          elevenlabs_voice_id: voicePrefs.elevenlabs_voice_id,
          save_tag: editTag || undefined,
          save_index: editTag ? index : undefined,
          profile
        });
        if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
        const url = URL.createObjectURL(blob);
        previewUrlRef.current = url;
        if (!audioRef.current) audioRef.current = new Audio();
        const el = audioRef.current;
        el.src = url;
        await el.play();
        if (editTag) await load({ soft: true, profile });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Apercu voix impossible");
      } finally {
        setPlayingLineId(null);
      }
    },
    [editTag, load, profile, voicePrefs]
  );

  const confirmDelete = useCallback(async () => {
    if (!deleteTag) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteKbIntent(deleteTag);
      setDeleteTag(null);
      await load({ soft: true, profile });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur suppression");
    } finally {
      setDeleting(false);
    }
  }, [deleteTag, load, profile]);

  const runRegen = useCallback(async () => {
    setRegenBusy(true);
    setRegenMsg(null);
    try {
      const r = await regenerateKbVoices({
        force: true,
        profile,
        tts_provider: voicePrefs.tts_provider,
        edge_tts_voice: voicePrefs.edge_tts_voice,
        edge_tts_rate: voicePrefs.edge_tts_rate,
        edge_tts_pitch: voicePrefs.edge_tts_pitch,
        tts_voice_gain_db: voicePrefs.tts_voice_gain_db,
        elevenlabs_voice_id: voicePrefs.elevenlabs_voice_id
      });
      setRegenMsg(`Voix: ${r.ok} ok, ${r.skipped} ignorees, ${r.failed} echecs`);
      await load({ soft: true, profile });
    } catch (e) {
      setRegenMsg(e instanceof Error ? e.message : "Echec regen");
    } finally {
      setRegenBusy(false);
    }
  }, [load, profile, voicePrefs]);

  const profileLabel =
    profile === "outbound_commercial" ? "Appels commerciaux" : "Appels entrants";

  return (
    <AppLayout title="Base de connaissances" hidePageHeader>
      <VgPageHeader
        title="Base de connaissances"
        subtitle="Deux catalogues (entrant / commercial), CRUD, voix TTS. Le tchatche est sur le simulateur."
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
              size="small"
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={() => void load({ soft: intents.length > 0, profile })}
              disabled={loading || syncing}
            >
              Actualiser
            </Button>
            <Button size="small" variant="outlined" startIcon={<AddIcon />} onClick={openCreate}>
              Nouvel intent
            </Button>
          </Stack>
        }
      />

      <Tabs
        value={profile}
        onChange={(_, v: KbProfile) => setProfile(v)}
        sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}
      >
        <Tab value="inbound" label="Appels entrants" />
        <Tab value="outbound_commercial" label="Appels commerciaux" />
      </Tabs>

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
        title={`Voix TTS (${profileLabel})`}
        description="Meme reglage que l'accueil : moteur, voix, volume, debit, hauteur. Applique a la regen de ce catalogue."
      >
        <KbVoicePrefsPanel value={voicePrefs} onChange={patchVoice} disabled={regenBusy} />
        {voicePrefs.tts_provider === "elevenlabs" ? (
          <Box sx={{ mt: 2 }}>
            <ElevenLabsKeysPanel />
          </Box>
        ) : null}
        {voiceSaveMsg ? (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
            {voiceSaveMsg}
          </Typography>
        ) : null}
        <Box sx={{ mt: 2 }}>
          <Button
            size="small"
            variant="contained"
            startIcon={<RecordVoiceOverIcon />}
            onClick={() => void runRegen()}
            disabled={regenBusy || loading}
          >
            {regenBusy ? "Generation…" : "Regenerer les voix de ce catalogue"}
          </Button>
        </Box>
      </VgSettingsSection>

      <VgSettingsSection
        title={`Intents ${profileLabel} (${intents.length})`}
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
            {profileGroups.map((g) => (
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
        ) : !intents.length ? (
          <Typography variant="body2" color="text.secondary" sx={{ py: 3 }}>
            Catalogue vide. Cree un intent ou reimporte un seed quand tu seras pret.
          </Typography>
        ) : (
          profileGroups.map((g) => {
            const rows = grouped[g.id] || [];
            if (!rows.length) return null;
            return (
              <Accordion
                key={`${profile}-${g.id}`}
                defaultExpanded={g.id === expandedDefault || groupFilter === g.id}
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
                  <Box
                    sx={{
                      display: "grid",
                      gridTemplateColumns: {
                        xs: "1fr",
                        sm: "repeat(2, minmax(0, 1fr))",
                        lg: "repeat(3, minmax(0, 1fr))"
                      },
                      gap: 1.25
                    }}
                  >
                    {rows.map((row) => (
                      <Box
                        key={row.tag}
                        sx={{
                          p: 1.25,
                          borderRadius: 1.5,
                          border: "1px solid",
                          borderColor: "divider",
                          bgcolor: "background.paper",
                          display: "flex",
                          flexDirection: "column",
                          gap: 1,
                          minHeight: 132
                        }}
                      >
                        <Stack
                          direction="row"
                          spacing={0.5}
                          sx={{ alignItems: "center", flexWrap: "wrap", gap: 0.5 }}
                        >
                          <Typography
                            variant="body2"
                            sx={{
                              fontWeight: 700,
                              fontFamily: "ui-monospace, monospace",
                              fontSize: "0.8rem"
                            }}
                            noWrap
                            title={row.tag}
                          >
                            {row.tag}
                          </Typography>
                          {!row.enabled ? <Chip size="small" label="off" /> : null}
                          {row.action ? (
                            <Chip size="small" variant="outlined" label={row.action} />
                          ) : null}
                          <Chip
                            size="small"
                            variant="outlined"
                            label={`prio ${row.priority}`}
                          />
                        </Stack>
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          title={row.responses[0] || ""}
                          sx={{
                            flex: 1,
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                            lineHeight: 1.35,
                            fontSize: "0.8125rem"
                          }}
                        >
                          {row.responses[0] || "—"}
                        </Typography>
                        <Stack
                          direction="row"
                          spacing={0.5}
                          sx={{
                            alignItems: "center",
                            justifyContent: "space-between",
                            mt: "auto"
                          }}
                        >
                          <Typography variant="caption" color="text.secondary">
                            {row.patterns.length}p · {row.responses.length}r
                          </Typography>
                          <Stack direction="row" spacing={0.25}>
                            <IconButton
                              size="small"
                              aria-label={row.has_wav ? "ecouter" : "wav absent"}
                              disabled={!row.has_wav}
                              onClick={() => playVoice(row.tag)}
                              color={row.has_wav ? "primary" : "default"}
                            >
                              <PlayArrowIcon fontSize="small" />
                            </IconButton>
                            <IconButton
                              size="small"
                              aria-label="modifier"
                              onClick={() => openEdit(row)}
                            >
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
                  </Box>
                </AccordionDetails>
              </Accordion>
            );
          })
        )}
      </VgSettingsSection>

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        fullWidth
        maxWidth="md"
        scroll="paper"
      >
        <DialogTitle>
          {editTag ? `Modifier ${editTag}` : `Nouvel intent (${profileLabel})`}
        </DialogTitle>
        <DialogContent dividers sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr", sm: "1.4fr 0.7fr 1fr auto" },
              gap: 1.25,
              alignItems: "start"
            }}
          >
            {!editTag ? (
              <TextField
                label="Tag (ex. mon_intent)"
                size="small"
                value={form.tag}
                onChange={(e) => setForm((f) => ({ ...f, tag: e.target.value }))}
                helperText="Minuscules, chiffres, underscore"
              />
            ) : (
              <TextField
                label="Tag"
                size="small"
                value={editTag}
                disabled
              />
            )}
            <TextField
              label="Priorite"
              size="small"
              type="number"
              value={form.priority}
              onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}
            />
            <TextField
              label="Action"
              size="small"
              value={form.action}
              onChange={(e) => setForm((f) => ({ ...f, action: e.target.value }))}
              placeholder="hangup_soft…"
            />
            <FormControlLabel
              sx={{ m: 0, mt: { xs: 0, sm: 0.5 } }}
              control={
                <Switch
                  checked={form.enabled}
                  onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
                />
              }
              label="Active"
            />
          </Box>

          <KbIntentLinesEditor
            title="Patterns"
            hint="Ce que le prospect peut dire (STT). Une carte = un pattern."
            dense
            items={form.patterns}
            onChange={(patterns) => setForm((f) => ({ ...f, patterns }))}
            placeholder="ex. bonjour"
          />

          <KbIntentLinesEditor
            title="Reponses"
            hint="Une carte = une formulation. Play = TTS avec la voix courante (sans regen tout le catalogue)."
            markFirstAsVoice
            items={form.responses}
            onChange={(responses) => setForm((f) => ({ ...f, responses }))}
            onPlay={playResponsePreview}
            playingId={playingLineId}
            placeholder="Phrase a dire…"
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 1.5, gap: 1 }}>
          {saveOk ? (
            <Typography variant="body2" color="success.main" sx={{ mr: "auto" }}>
              Enregistre
            </Typography>
          ) : (
            <Box sx={{ mr: "auto" }} />
          )}
          <Button onClick={() => setDialogOpen(false)}>Fermer</Button>
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
