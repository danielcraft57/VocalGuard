"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import CloudUploadOutlinedIcon from "@mui/icons-material/CloudUploadOutlined";
import InsightsOutlinedIcon from "@mui/icons-material/InsightsOutlined";
import TableRowsOutlinedIcon from "@mui/icons-material/TableRowsOutlined";
import CallOutlinedIcon from "@mui/icons-material/CallOutlined";
import SearchIcon from "@mui/icons-material/Search";
import AddIcon from "@mui/icons-material/Add";
import DeleteSweepOutlinedIcon from "@mui/icons-material/DeleteSweepOutlined";
import CloseIcon from "@mui/icons-material/Close";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Fade,
  FormControl,
  IconButton,
  InputAdornment,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { AppLayout } from "../../components/AppLayout";
import { VgTableSkeleton } from "../../components/mui/VgListSkeleton";
import { VerificationProspectsTable } from "./components/VerificationProspectsTable";
import {
  emptyProspectForm,
  formFromProspect,
  ProspectPhoneFormDialog,
  ProspectPhoneFormValues,
} from "./components/ProspectPhoneFormDialog";
import { ProspectPhoneDetailDialog } from "./components/ProspectPhoneDetailDialog";
import { cityLabelFromUploadFilename } from "./prospectDisplayUtils";
import {
  IDLE_PIPELINE,
  pipelinePatchFromImportSummary,
  useProspectPhonePipelineRealtime,
  type ProspectEnrichRowPatch,
} from "./hooks/useProspectPhonePipelineRealtime";
import {
  OsintStatusChip,
  ProspectLabStatusChip,
  NameMatchChip,
  OSINT_STATUS_LABELS,
  PROSPECTLAB_STATUS_LABELS,
  MATCH_STATUS_LABELS,
} from "./prospectStatusUi";
import {
  clearPersistedImportBatchId,
  loadPersistedImportBatchId,
  savePersistedImportBatchId,
} from "../../services/prospectPhonesUiPersist";
import {
  fetchProspectPhones,
  fetchProspectPhoneSourceCities,
  fetchProspectPhonesSummary,
  fetchProspectEnrichCapabilities,
  fetchProspectImportBatch,
  importProspectPhonesDirectory,
  importProspectPhonesXlsx,
  fetchProspectServerLogs,
  ProspectPhone,
  ProspectEnrichCapabilities,
  ProspectPhoneVerificationStatus,
  updateProspectPhone,
  createProspectPhone,
  deleteProspectPhone,
  deleteAllProspectPhones,
} from "../../services/prospectPhonesApi";

const BATCH_PHASE_LABELS: Record<string, string> = {
  pending: "En attente",
  import: "Import Excel",
  enrich: "OSINT en cours",
  done: "Termine",
  failed: "Echec",
};

const STATUS_LABELS: Record<ProspectPhoneVerificationStatus, string> = {
  pending: "A verifier",
  line_ok: "Ligne OK",
  line_fail: "Ligne morte",
  voicemail: "Repondeur",
  company_ok: "Bonne entreprise",
  company_mismatch: "Mauvaise entreprise",
  skipped: "Ignore",
};

const cardSx = {
  borderRadius: 3,
  border: "1px solid var(--vg-color-border-subtle)",
  bgcolor: "var(--vg-color-surface)",
  boxShadow: "0 8px 28px rgba(15, 23, 42, 0.05)",
  transition: "transform .22s ease, box-shadow .22s ease",
  "&:hover": { transform: "translateY(-2px)", boxShadow: "0 14px 36px rgba(15, 23, 42, 0.08)" },
};

/**
 * Page qualification telephonique : import, suivi live, tableau filtrable.
 */
export default function VerificationProspectsPage(): React.ReactElement {
  const [items, setItems] = useState<ProspectPhone[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [limit] = useState(50);
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [sourceCity, setSourceCity] = useState("");
  const [statusFilter, setStatusFilter] = useState<ProspectPhoneVerificationStatus | "">("");
  const [osintFilter, setOsintFilter] = useState("");
  const [plFilter, setPlFilter] = useState("");
  const [matchFilter, setMatchFilter] = useState("");
  const [sourceCities, setSourceCities] = useState<string[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [runOsint, setRunOsint] = useState(true);
  const [dragOver, setDragOver] = useState(false);
  const [serverLogs, setServerLogs] = useState<{ at: string; level: string; message: string }[]>([]);
  const [activeBatchId, setActiveBatchId] = useState<number | null>(null);
  const [activeBatchCity, setActiveBatchCity] = useState<string | null>(null);
  /** Suivi live import/OSINT (separe du filtre « Lot # » pour ne pas rouvrir l'analyse). */
  const [pipelineBatchId, setPipelineBatchId] = useState<number | null>(null);
  const [editor, setEditor] = useState<"create" | ProspectPhone | null>(null);
  const [detailProspectId, setDetailProspectId] = useState<number | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ProspectPhone | "all" | null>(null);
  const [saving, setSaving] = useState(false);
  const [pipeline, setPipeline] = useState(IDLE_PIPELINE);
  const [enrichCaps, setEnrichCaps] = useState<ProspectEnrichCapabilities | null>(null);
  const [pipelineRestored, setPipelineRestored] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQ(q.trim()), 320);
    return () => window.clearTimeout(t);
  }, [q]);

  const reloadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchProspectPhones({
        skip,
        limit,
        q: debouncedQ || undefined,
        source_city: sourceCity || undefined,
        verification_status: statusFilter || undefined,
        osint_status: osintFilter || undefined,
        prospectlab_status: plFilter || undefined,
        name_match_status: matchFilter || undefined,
        import_batch_id: activeBatchId ?? undefined,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chargement impossible");
    } finally {
      setLoading(false);
    }
  }, [skip, limit, debouncedQ, sourceCity, statusFilter, osintFilter, plFilter, matchFilter, activeBatchId]);

  const reloadMeta = useCallback(async () => {
    try {
      const [cities, sum] = await Promise.all([fetchProspectPhoneSourceCities(), fetchProspectPhonesSummary()]);
      setSourceCities(cities);
      setSummary(sum.by_status ?? {});
    } catch {
      // meta optionnelle
    }
  }, []);

  useEffect(() => { void reloadList(); }, [reloadList]);
  useEffect(() => { void reloadMeta(); }, [reloadMeta]);

  useEffect(() => {
    void fetchProspectEnrichCapabilities()
      .then(setEnrichCaps)
      .catch(() => setEnrichCaps(null));
  }, []);

  const clearPipelineUi = useCallback(() => {
    clearPersistedImportBatchId();
    setPipelineBatchId(null);
    setPipeline(IDLE_PIPELINE);
  }, []);

  useEffect(() => {
    if (pipelineRestored) return;
    const storedId = loadPersistedImportBatchId();
    if (!storedId) {
      setPipelineRestored(true);
      return;
    }
    void fetchProspectImportBatch(storedId)
      .then((summary) => {
        const patch = pipelinePatchFromImportSummary(summary);
        if (patch.phase === "done" || patch.phase === "failed" || patch.phase === "idle") {
          clearPersistedImportBatchId();
          return;
        }
        setActiveBatchId(storedId);
        setActiveBatchCity(summary.source_city?.trim() || null);
        setPipelineBatchId(storedId);
        setPipeline({
          ...IDLE_PIPELINE,
          ...patch,
          logLine:
            patch.phase === "enrich"
              ? "Reprise de l'analyse du dernier import…"
              : "Reprise de l'import en cours…",
          enrichEngine: enrichCaps?.enrich_engine ?? null,
          enrichParallel: enrichCaps?.default_parallel ?? null,
        });
      })
      .catch(() => clearPersistedImportBatchId())
      .finally(() => setPipelineRestored(true));
  }, [enrichCaps, pipelineRestored]);

  useEffect(() => {
    if (pipeline.phase !== "done") return;
    const t = window.setTimeout(() => clearPipelineUi(), 10000);
    return () => window.clearTimeout(t);
  }, [pipeline.phase, clearPipelineUi]);

  const mergeProspectFromEnrich = useCallback((patch: ProspectEnrichRowPatch) => {
    setItems((prev) => {
      const idx = prev.findIndex((x) => x.id === patch.id);
      if (idx < 0) return prev;
      const next = [...prev];
      next[idx] = { ...next[idx], ...patch };
      return next;
    });
  }, []);

  useEffect(() => {
    let stop = false;
    const pull = () => {
      void fetchProspectServerLogs()
        .then((lines) => {
          if (!stop) setServerLogs(lines);
        })
        .catch(() => {
          // le journal est optionnel si l'API est coupee
        });
    };
    pull();
    const id = window.setInterval(pull, 4000);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, []);

  useProspectPhonePipelineRealtime({
    pipelineBatchId,
    onState: (patch) => setPipeline((prev) => ({ ...prev, ...patch })),
    onRefreshList: () => { void reloadList(); void reloadMeta(); },
    onProspectRow: (row, step) => {
      mergeProspectFromEnrich(row);
      if (step === "done" || step === "failed") {
        void reloadList();
      }
    },
    onPipelineComplete: () => {
      clearPersistedImportBatchId();
      setPipelineBatchId(null);
    },
  });

  const handleFiles = async (files: FileList | File[] | null) => {
    if (!files?.length) return;
    setImporting(true);
    setError(null);
    setPipeline({ phase: "import", importSummary: null, importPercent: 4, enrichPercent: null, logLine: "Lecture du fichier…" });
    try {
      const list = Array.from(files);
      for (const file of list) {
        const summary = await importProspectPhonesXlsx(file, runOsint);
        setActiveBatchId(summary.batch_id);
        setActiveBatchCity(summary.source_city?.trim() || cityLabelFromUploadFilename(file.name));
        setPipelineBatchId(summary.batch_id);
        savePersistedImportBatchId(summary.batch_id);
        const villeLabel = summary.source_city?.trim() || cityLabelFromUploadFilename(file.name);
        setPipeline((p) => ({
          ...p,
          ...pipelinePatchFromImportSummary(summary),
          phase: "import",
          logLine: villeLabel ? `Import ${villeLabel} en cours…` : "Import en cours…",
          enrichEngine: enrichCaps?.enrich_engine ?? null,
          enrichParallel: enrichCaps?.default_parallel ?? null,
        }));
      }
    } catch (e) {
      setPipeline((p) => ({ ...p, phase: "failed", logLine: e instanceof Error ? e.message : "Import echoue" }));
      setError(e instanceof Error ? e.message : "Import echoue");
      setImporting(false);
    }
  };

  useEffect(() => {
    if (pipeline.phase === "done" || pipeline.phase === "failed") setImporting(false);
  }, [pipeline.phase]);

  const handleStatusChange = async (row: ProspectPhone, status: ProspectPhoneVerificationStatus) => {
    const previous = items;
    setItems((prev) => prev.map((x) => (x.id === row.id ? { ...x, verification_status: status } : x)));
    try {
      const updated = await updateProspectPhone(row.id, { verification_status: status });
      setItems((prev) => prev.map((x) => (x.id === row.id ? updated : x)));
      void reloadMeta();
    } catch (e) {
      setItems(previous);
      setError(e instanceof Error ? e.message : "Mise a jour impossible");
    }
  };

  const handleSave = async (values: ProspectPhoneFormValues) => {
    setSaving(true);
    setError(null);
    const payload = {
      name: values.name.trim(),
      phone_number: values.phone_number.trim() || null,
      source_city: values.source_city.trim() || null,
      address_1: values.address_1.trim() || null,
      address_2: values.address_2.trim() || null,
      verification_status: values.verification_status,
      verification_notes: values.verification_notes.trim() || null,
    };
    try {
      if (editor && editor !== "create") {
        await updateProspectPhone(editor.id, payload);
      } else {
        await createProspectPhone(payload);
      }
      setEditor(null);
      await reloadList();
      await reloadMeta();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Enregistrement impossible");
    } finally {
      setSaving(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    setSaving(true);
    setError(null);
    try {
      if (pendingDelete === "all") {
        await deleteAllProspectPhones();
        setActiveBatchId(null);
        setSkip(0);
      } else {
        await deleteProspectPhone(pendingDelete.id);
      }
      setPendingDelete(null);
      await reloadList();
      await reloadMeta();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Suppression impossible");
    } finally {
      setSaving(false);
    }
  };

  const pageCount = useMemo(() => Math.max(1, Math.ceil(total / limit)), [total, limit]);
  const pageIndex = Math.floor(skip / limit) + 1;
  const live = pipeline.phase === "import" || pipeline.phase === "enrich";
  const analyseVisible = pipeline.phase !== "idle";

  return (
    <AppLayout title="Qualification telephonique" hidePageHeader>
      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={2}
        sx={{ mb: 3, justifyContent: "space-between", alignItems: { md: "flex-end" } }}
      >
        <Box>
          <Typography variant="overline" sx={{ color: "var(--vg-color-primary)", letterSpacing: ".14em", fontWeight: 700 }}>
            Import Excel
          </Typography>
          <Typography variant="h4" sx={{ fontWeight: 750, letterSpacing: "-0.03em", lineHeight: 1.15, fontSize: { xs: "1.55rem", sm: "2rem" } }}>
            Qualification telephonique
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, maxWidth: 560 }}>
            Depose un Excel par ville, enrichis en OSINT, puis valide chaque numero avant d'appeler.
          </Typography>
        </Box>
        <Button component={Link} href="/calls" variant="contained" startIcon={<CallOutlinedIcon />} sx={{ borderRadius: 999, px: 2.4 }}>
          Appels sortants
        </Button>
      </Stack>

      <Stack direction={{ xs: "column", lg: "row" }} spacing={2} sx={{ mb: 2.5 }}>
        <Card sx={{ ...cardSx, flex: 1.2 }}>
          <CardContent>
            <Stack direction="row" spacing={1} sx={{ mb: 1.5, alignItems: "center" }}>
              <CloudUploadOutlinedIcon color="primary" />
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>1. Upload</Typography>
            </Stack>
            <Box
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                void handleFiles(e.dataTransfer.files);
              }}
              sx={{
                borderRadius: 3,
                border: "1.5px dashed",
                borderColor: dragOver ? "var(--vg-color-primary)" : "var(--vg-color-border)",
                bgcolor: dragOver ? "var(--vg-color-primary-soft)" : "var(--vg-color-bg)",
                py: 3.2,
                px: 2,
                textAlign: "center",
                transition: "border-color .2s ease, background-color .2s ease, transform .2s ease",
                transform: dragOver ? "scale(1.015)" : "none",
              }}
            >
              <Typography variant="body2" sx={{ fontWeight: 650 }}>Glisse tes .xlsx ici</Typography>
              <Typography variant="caption" component="div" color="text.secondary" sx={{ mb: 1.5 }}>
                Un fichier par ville. La ville est lue dans le Excel ou deduite du nom du fichier.
              </Typography>
              <Button variant="contained" component="label" disabled={importing} sx={{ borderRadius: 999 }}>
                Choisir des fichiers
                <input hidden type="file" accept=".xlsx" multiple onChange={(e) => void handleFiles(e.target.files)} />
              </Button>
            </Box>
            <Stack direction="row" sx={{ mt: 1.5, alignItems: "center", justifyContent: "space-between" }}>
              <Box>
                <Typography variant="body2">Enrichir OSINT + ProspectLab</Typography>
                {enrichCaps ? (
                  <Typography variant="caption" component="div" color="text.secondary">
                    {enrichCaps.osint_remote
                      ? `Moteur ${enrichCaps.enrich_engine} (${enrichCaps.osint_host ?? "distant"}) · x${enrichCaps.default_parallel} en parallele`
                      : "Moteur local (lent) — mets OSINT_SERVICE_URL=http://node15.lan:8110 dans .env"}
                  </Typography>
                ) : null}
              </Box>
              <Switch checked={runOsint} onChange={(e) => setRunOsint(e.target.checked)} />
            </Stack>
            <Button
              fullWidth
              variant="text"
              disabled={importing}
              onClick={() => void importProspectPhonesDirectory().then(() => { void reloadList(); void reloadMeta(); })}
            >
              Ou importer le dossier serveur
            </Button>
          </CardContent>
        </Card>

        <Card sx={{ ...cardSx, flex: 1 }}>
          <CardContent>
            <Stack direction="row" spacing={1} sx={{ mb: 1.5, alignItems: "center" }}>
              <InsightsOutlinedIcon color="secondary" />
              <Typography variant="subtitle1" sx={{ fontWeight: 700, flex: 1 }}>2. Analyse</Typography>
              {live ? (
                <Chip
                  size="small"
                  color="primary"
                  label="en cours"
                  sx={{
                    animation: "vgPulse 1.4s ease infinite",
                    "@keyframes vgPulse": { "0%,100%": { opacity: 1 }, "50%": { opacity: 0.55 } },
                  }}
                />
              ) : null}
              {analyseVisible ? (
                <Tooltip title="Masquer l'avancement">
                  <IconButton size="small" aria-label="Masquer l'avancement" onClick={clearPipelineUi}>
                    <CloseIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              ) : null}
            </Stack>
            {pipeline.phase === "done" ? (
              <Alert
                severity="success"
                icon={<CheckCircleOutlinedIcon fontSize="inherit" />}
                sx={{ mb: 1.5 }}
                action={
                  <Button color="inherit" size="small" onClick={clearPipelineUi}>
                    Masquer
                  </Button>
                }
              >
                Import et analyse termines. Le panneau se ferme tout seul dans quelques secondes.
              </Alert>
            ) : null}
            <Typography variant="body2" color="text.secondary" sx={{ minHeight: analyseVisible ? 40 : 24, mb: 1 }}>
              {analyseVisible ? (pipeline.logLine ?? "…") : "En attente d'un fichier."}
            </Typography>
            <Collapse in={analyseVisible && pipeline.importPercent != null}>
              <Typography variant="caption">Import Excel</Typography>
              <LinearProgress variant="determinate" value={pipeline.importPercent ?? 0} sx={{ height: 8, borderRadius: 99, mb: 1.2 }} />
            </Collapse>
            <Collapse in={analyseVisible && (pipeline.phase === "enrich" || pipeline.phase === "done" || pipeline.enrichPercent != null)}>
              <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", mb: 0.4 }}>
                <Typography variant="caption">OSINT / ProspectLab</Typography>
                {pipeline.enrichEngine ? (
                  <Typography variant="caption" color="text.secondary">
                    {pipeline.enrichParallel && pipeline.enrichParallel > 1
                      ? `${pipeline.enrichEngine} · x${pipeline.enrichParallel}`
                      : pipeline.enrichEngine}
                  </Typography>
                ) : null}
              </Stack>
              <LinearProgress color="secondary" variant="determinate" value={pipeline.enrichPercent ?? 0} sx={{ height: 8, borderRadius: 99, mb: 1.2 }} />
            </Collapse>
            <Collapse in={analyseVisible && Boolean(pipeline.activeProspect || pipeline.lastProspect)}>
              <Paper
                variant="outlined"
                sx={{
                  p: 1.2,
                  mb: 1.2,
                  borderRadius: 2,
                  bgcolor: "var(--vg-color-bg)",
                  borderColor: "var(--vg-color-border-subtle)",
                }}
              >
                {pipeline.activeProspect ? (
                  <>
                    <Typography variant="caption" color="primary" sx={{ fontWeight: 700 }}>
                      En cours
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 650, mt: 0.3 }}>
                      {pipeline.activeProspect.name}
                    </Typography>
                    <Typography variant="caption" component="div" color="text.secondary">
                      {pipeline.activeProspect.phone_number ?? ""}
                    </Typography>
                  </>
                ) : null}
                {pipeline.lastProspect ? (
                  <>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                      {pipeline.activeProspect ? "Dernier termine" : "Dernier resultat"}
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, mt: 0.3 }}>
                      {pipeline.lastProspect.name}
                    </Typography>
                    <Stack direction="row" spacing={0.5} sx={{ mt: 0.6, flexWrap: "wrap", gap: 0.4 }}>
                      <OsintStatusChip status={pipeline.lastProspect.osint_status ?? "pending"} />
                      <ProspectLabStatusChip status={pipeline.lastProspect.prospectlab_status ?? "pending"} />
                      {pipeline.lastProspect.name_match_status ? (
                        <NameMatchChip status={pipeline.lastProspect.name_match_status} />
                      ) : null}
                    </Stack>
                  </>
                ) : null}
              </Paper>
            </Collapse>
            <Fade in={analyseVisible && Boolean(pipeline.importSummary)}>
              <Stack direction="row" spacing={0.6} sx={{ flexWrap: "wrap", gap: 0.6 }}>
                {pipeline.importSummary?.source_city ? (
                  <Chip size="small" color="primary" variant="outlined" label={pipeline.importSummary.source_city} />
                ) : null}
                <Chip
                  size="small"
                  variant="outlined"
                  label={BATCH_PHASE_LABELS[pipeline.importSummary?.phase ?? ""] ?? pipeline.importSummary?.phase ?? "—"}
                />
                <Chip size="small" color="success" variant="outlined" label={`${pipeline.importSummary?.imported_rows ?? 0} importes`} />
                <Chip size="small" color="info" variant="outlined" label={`${pipeline.importSummary?.enrich_done ?? 0} OSINT`} />
              </Stack>
            </Fade>
            {pipeline.importSummary?.last_error ? <Alert severity="warning" sx={{ mt: 1.5 }}>{pipeline.importSummary.last_error}</Alert> : null}
            <Box
              sx={{
                mt: 1.5,
                p: 1.2,
                borderRadius: 2,
                bgcolor: "#0b1220",
                color: "#d6e2f0",
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                fontSize: 12,
                lineHeight: 1.45,
                maxHeight: 180,
                overflow: "auto",
              }}
            >
              <Typography variant="caption" component="div" sx={{ color: "#8ea0b8", mb: 0.6 }}>
                Journal backend
              </Typography>
              {serverLogs.length === 0 ? (
                <span>Aucune erreur recente. Les plantages SQL et d'import s'affichent ici.</span>
              ) : (
                serverLogs.map((line, i) => (
                  <div key={`${line.at}-${i}`}>
                    <span style={{ color: line.level === "ERROR" ? "#ff8a80" : "#ffd180" }}>{line.at} {line.level}</span>
                    {" "}
                    {line.message}
                  </div>
                ))
              )}
            </Box>
          </CardContent>
        </Card>
      </Stack>

      <Card sx={{ ...cardSx, "&:hover": { transform: "none", boxShadow: cardSx.boxShadow } }}>
        <CardContent>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 2, alignItems: { sm: "center" } }}>
            <Stack direction="row" spacing={1} sx={{ flex: 1, alignItems: "center" }}>
              <TableRowsOutlinedIcon color="primary" />
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>3. Resultats</Typography>
              <Chip size="small" label={`${total}`} />
            </Stack>
            {Object.entries(summary).slice(0, 4).map(([k, v]) => (
              <Chip
                key={k}
                size="small"
                variant="outlined"
                label={`${STATUS_LABELS[k as ProspectPhoneVerificationStatus] ?? k} ${v}`}
                onClick={() => {
                  setSkip(0);
                  setStatusFilter(k as ProspectPhoneVerificationStatus);
                }}
              />
            ))}
            {activeBatchId ? (
              <Chip
                color="primary"
                size="small"
                label={activeBatchCity ? `Ville : ${activeBatchCity}` : "Dernier import"}
                onDelete={() => {
                  setActiveBatchId(null);
                  setActiveBatchCity(null);
                }}
              />
            ) : null}
            <Button size="small" variant="outlined" startIcon={<AddIcon />} sx={{ borderRadius: 999 }} onClick={() => setEditor("create")}>
              Ajouter
            </Button>
            <Button
              size="small"
              color="error"
              variant="outlined"
              startIcon={<DeleteSweepOutlinedIcon />}
              sx={{ borderRadius: 999 }}
              disabled={total === 0}
              onClick={() => setPendingDelete("all")}
            >
              Tout supprimer
            </Button>
          </Stack>

          <Box
            sx={{
              mb: 2,
              display: "grid",
              gap: 1.2,
              gridTemplateColumns: { xs: "1fr 1fr", md: "minmax(180px, 1.4fr) repeat(4, minmax(120px, 1fr))" },
            }}
          >
            <TextField
              size="small"
              fullWidth
              placeholder="Nom, telephone, adresse…"
              value={q}
              onChange={(e) => { setSkip(0); setQ(e.target.value); }}
              slotProps={{
                input: {
                  startAdornment: (
                    <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>
                  ),
                },
              }}
              sx={{ gridColumn: { xs: "1 / -1", md: "auto" }, "& .MuiOutlinedInput-root": { borderRadius: 999, bgcolor: "var(--vg-color-bg)" } }}
            />
            <FormControl size="small" fullWidth>
              <InputLabel>Ville</InputLabel>
              <Select label="Ville" value={sourceCity} onChange={(e) => { setSkip(0); setSourceCity(e.target.value); }}>
                <MenuItem value="">Toutes</MenuItem>
                {sourceCities.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
              </Select>
            </FormControl>
            <FormControl size="small" fullWidth>
              <InputLabel>OSINT</InputLabel>
              <Select label="OSINT" value={osintFilter} onChange={(e) => { setSkip(0); setOsintFilter(e.target.value); }}>
                <MenuItem value="">Tous</MenuItem>
                {["pending", "queued", "done", "failed"].map((s) => (
                  <MenuItem key={s} value={s}>{OSINT_STATUS_LABELS[s] ?? s}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl size="small" fullWidth>
              <InputLabel>ProspectLab</InputLabel>
              <Select label="ProspectLab" value={plFilter} onChange={(e) => { setSkip(0); setPlFilter(e.target.value); }}>
                <MenuItem value="">Tous</MenuItem>
                {["pending", "matched", "not_found"].map((s) => (
                  <MenuItem key={s} value={s}>{PROSPECTLAB_STATUS_LABELS[s] ?? s}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl size="small" fullWidth>
              <InputLabel>Match nom</InputLabel>
              <Select label="Match nom" value={matchFilter} onChange={(e) => { setSkip(0); setMatchFilter(e.target.value); }}>
                <MenuItem value="">Tous</MenuItem>
                {["match", "partial", "mismatch", "unknown"].map((s) => (
                  <MenuItem key={s} value={s}>{MATCH_STATUS_LABELS[s] ?? s}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>

          <Collapse in={Boolean(error)}>
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>
          </Collapse>

          {loading && items.length === 0 ? (
            <VgTableSkeleton rows={8} />
          ) : (
            <Fade in timeout={280}>
              <Box>
                <VerificationProspectsTable
                  rows={items}
                  statusLabels={STATUS_LABELS}
                  enrichingProspectId={pipeline.activeProspect?.id ?? null}
                  onStatusChange={(r, s) => void handleStatusChange(r, s)}
                  onEdit={(row) => setEditor(row)}
                  onDelete={(row) => setPendingDelete(row)}
                  onViewDetail={(row) => setDetailProspectId(row.id)}
                />
                <Stack direction="row" sx={{ mt: 2, justifyContent: "space-between", alignItems: "center" }}>
                  <Typography variant="body2" color="text.secondary">
                    Page {pageIndex} / {pageCount}
                  </Typography>
                  <Stack direction="row" spacing={1}>
                    <Button size="small" variant="outlined" sx={{ borderRadius: 999 }} disabled={skip <= 0} onClick={() => setSkip(Math.max(0, skip - limit))}>
                      Precedent
                    </Button>
                    <Button size="small" variant="outlined" sx={{ borderRadius: 999 }} disabled={skip + limit >= total} onClick={() => setSkip(skip + limit)}>
                      Suivant
                    </Button>
                  </Stack>
                </Stack>
              </Box>
            </Fade>
          )}
        </CardContent>
      </Card>
      <ProspectPhoneDetailDialog
        open={detailProspectId !== null}
        prospectId={detailProspectId}
        fallbackProspect={
          detailProspectId != null ? items.find((x) => x.id === detailProspectId) ?? null : null
        }
        statusLabels={STATUS_LABELS}
        onClose={() => setDetailProspectId(null)}
        onUpdated={(prospect) => {
          setItems((prev) => prev.map((x) => (x.id === prospect.id ? prospect : x)));
          void reloadMeta();
        }}
      />
      <ProspectPhoneFormDialog
        key={editor === "create" ? "create" : editor ? String(editor.id) : "closed"}
        open={editor !== null}
        title={editor && editor !== "create" ? "Modifier le prospect" : "Nouveau prospect"}
        initial={editor && editor !== "create" ? formFromProspect(editor) : emptyProspectForm()}
        statusLabels={STATUS_LABELS}
        saving={saving}
        onClose={() => setEditor(null)}
        onSubmit={(values) => void handleSave(values)}
      />
      <Dialog open={pendingDelete !== null} onClose={saving ? undefined : () => setPendingDelete(null)}>
        <DialogTitle>{pendingDelete === "all" ? "Supprimer tous les resultats ?" : "Supprimer ce prospect ?"}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            {pendingDelete === "all"
              ? "Ca efface toute la liste, les categories et les lots d'import. Les appels deja passes restent."
              : pendingDelete
                ? `${pendingDelete.name} sera retire de la liste.`
                : ""}
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setPendingDelete(null)} disabled={saving}>Annuler</Button>
          <Button color="error" variant="contained" disabled={saving} onClick={() => void handleConfirmDelete()}>
            {saving ? "Suppression…" : "Supprimer"}
          </Button>
        </DialogActions>
      </Dialog>
    </AppLayout>
  );
}
