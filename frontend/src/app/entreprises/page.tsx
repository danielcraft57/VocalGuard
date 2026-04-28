"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Box, Card, CardContent, Stack, Typography } from "@mui/material";
import { AppLayout } from "../../components/AppLayout";
import {
  fetchEntreprises,
  importEntreprisesXlsx,
  deleteEntreprise,
  deleteEntreprisesBulk,
  fetchEntrepriseCallStats,
  Entreprise,
  EntrepriseImportSummary,
} from "../../services/entreprisesApi";
import { EntreprisesFiltersBar } from "./components/EntreprisesFiltersBar";
import { EntreprisesListTable } from "./components/EntreprisesListTable";
import { EntrepriseDetailsDialog } from "./components/EntrepriseDetailsDialog";
import { EntrepriseImportPanel } from "./components/EntrepriseImportPanel";
import { EntreprisesPaginationBar } from "./components/EntreprisesPaginationBar";
import { useEntrepriseImportRealtime } from "./hooks/useEntrepriseImportRealtime";
import type { EntrepriseCallStats, EntrepriseDetailsTab, ImportProgressCounters, PhoneAvailabilityFilter } from "./types";

export default function EntreprisesPage() {
  const [entreprises, setEntreprises] = useState<Entreprise[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastImport, setLastImport] = useState<EntrepriseImportSummary | null>(null);
  const [analyzePhone, setAnalyzePhone] = useState(true);
  const [importProgress, setImportProgress] = useState<number | null>(null);
  const [importCounters, setImportCounters] = useState<ImportProgressCounters | null>(null);
  const [activeImportBatchId, setActiveImportBatchId] = useState<number | null>(null);

  const [skip, setSkip] = useState(0);
  const [limit, setLimit] = useState(50);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [city, setCity] = useState("");
  const [category, setCategory] = useState("");
  const [hasPhone, setHasPhone] = useState<PhoneAvailabilityFilter>("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [detailsEntreprise, setDetailsEntreprise] = useState<Entreprise | null>(null);
  const [callStats, setCallStats] = useState<EntrepriseCallStats | null>(null);
  const [detailsTab, setDetailsTab] = useState<EntrepriseDetailsTab>("infos");
  const osintReloadTimer = useRef<number | null>(null);
  const importUiResetTimer = useRef<number | null>(null);

  const entreprisesCount = useMemo(() => total, [total]);
  const page = useMemo(() => Math.floor(skip / limit) + 1, [skip, limit]);
  const pageCount = useMemo(() => Math.max(1, Math.ceil(total / limit)), [total, limit]);

  const reload = () => {
    setLoading(true);
    setError(null);
    fetchEntreprises({
      skip,
      limit,
      q: q.trim() || undefined,
      city: city.trim() || undefined,
      category: category.trim() || undefined,
      has_phone: hasPhone === "" ? undefined : hasPhone === "true",
    })
      .then((data) => {
        setEntreprises(data.items);
        setTotal(data.total);
        setSelectedIds([]);
      })
      .catch(() => setError("Impossible de charger les entreprises (verifie le backend)."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    reload();
  }, [skip, limit]);

  useEffect(() => {
    // Quand on change un filtre, on revient à la page 1
    setSkip(0);
    reload();
  }, [q, city, category, hasPhone]);

  useEntrepriseImportRealtime({
    activeBatchId: activeImportBatchId,
    onProgress: (pct, counters) => {
      if (typeof pct === "number") setImportProgress(pct);
      if (counters) setImportCounters(counters);
    },
    onCompleted: () => {
      setActiveImportBatchId(null);
      reload();
    },
    onOsintEvent: () => {
      // Débouncer: plusieurs tasks OSINT peuvent finir d'un coup
      if (osintReloadTimer.current) window.clearTimeout(osintReloadTimer.current);
      osintReloadTimer.current = window.setTimeout(() => {
        reload();
      }, 400);
    },
  });

  useEffect(() => {
    // Une fois à 100%, on "efface l'upload" (jauge + compteurs) après un court délai
    // pour laisser l'utilisateur voir la fin. Le résumé d'import (batch) reste affiché.
    if (importProgress !== 100) return;
    if (importUiResetTimer.current) window.clearTimeout(importUiResetTimer.current);
    importUiResetTimer.current = window.setTimeout(() => {
      setImportProgress(null);
      setImportCounters(null);
    }, 1200);
    return () => {
      if (importUiResetTimer.current) window.clearTimeout(importUiResetTimer.current);
    };
  }, [importProgress]);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    if (!file) return;
    setImporting(true);
    setError(null);
    setLastImport(null);
    setImportProgress(0);
    setImportCounters(null);
    try {
      const summary = await importEntreprisesXlsx(file, analyzePhone);
      setLastImport(summary);
      setActiveImportBatchId(summary.batch_id);
    } catch (err) {
      setError((err as Error)?.message ?? "Erreur import inconnue");
      setActiveImportBatchId(null);
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  };

  const toggleSelected = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleSelectAll = () => {
    if (selectedIds.length === entreprises.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(entreprises.map((x) => x.id));
    }
  };

  const handleDeleteOne = async (id: number) => {
    if (!confirm("Supprimer cette entreprise ?")) return;
    setError(null);
    try {
      await deleteEntreprise(id);
      reload();
    } catch (err) {
      setError((err as Error)?.message ?? "Erreur suppression inconnue");
    }
  };

  const handleDeleteSelected = async () => {
    if (selectedIds.length === 0) return;
    if (!confirm(`Supprimer ${selectedIds.length} entreprise(s) ?`)) return;
    setError(null);
    try {
      await deleteEntreprisesBulk(selectedIds);
      reload();
    } catch (err) {
      setError((err as Error)?.message ?? "Erreur suppression bulk inconnue");
    }
  };

  const handleOpenDetails = (e: Entreprise) => {
    setDetailsEntreprise(e);
    setCallStats(null);
    setDetailsTab("infos");
    setDetailsOpen(true);
  };

  useEffect(() => {
    if (!detailsOpen || !detailsEntreprise) return;
    fetchEntrepriseCallStats(detailsEntreprise.id)
      .then((s) => setCallStats(s))
      .catch(() => setCallStats({ total: 0, by_status: {} }));
  }, [detailsOpen, detailsEntreprise?.id]);

  const applyCityFilter = (v: string | null | undefined) => {
    if (!v) return;
    setCity(v);
  };

  const applyCategoryFilter = (v: string | null | undefined) => {
    if (!v) return;
    setCategory(v);
  };

  return (
    <AppLayout title="Entreprises" subtitle="Import Excel et liste des entreprises a prospecter (sans site web).">
      <EntrepriseImportPanel
        importing={importing}
        analyzePhone={analyzePhone}
        setAnalyzePhone={setAnalyzePhone}
        onFileChange={handleFileChange}
        progressPercent={importProgress}
        progressCounters={importCounters}
        lastImportSummary={lastImport}
        errorMessage={error}
      />

      <Card sx={{ mt: 2, borderRadius: 3, border: "1px solid var(--vg-color-border-subtle)", transition: "all .2s ease", "&:hover": { boxShadow: 6 } }}>
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
            <span className="material-icons" style={{ fontSize: 18 }}>business</span>
            <Typography variant="subtitle2">Entreprises ({loading ? "..." : entreprisesCount})</Typography>
          </Stack>

        <EntreprisesFiltersBar
          searchText={q}
          onSearchTextChange={setQ}
          city={city}
          onCityChange={setCity}
          category={category}
          onCategoryChange={setCategory}
          phoneFilter={hasPhone}
          onPhoneFilterChange={setHasPhone}
          pageSize={limit}
          onPageSizeChange={setLimit}
          loading={loading}
          selectedCount={selectedIds.length}
          onRefresh={reload}
          onDeleteSelection={handleDeleteSelected}
        />

        <EntreprisesPaginationBar
          page={page}
          pageCount={pageCount}
          total={total}
          loading={loading}
          canPrev={skip > 0}
          canNext={skip + limit < total}
          onPrev={() => setSkip(Math.max(0, skip - limit))}
          onNext={() => setSkip(Math.min((pageCount - 1) * limit, skip + limit))}
        />

        {loading ? (
          <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
            Chargement...
          </Typography>
        ) : entreprises.length === 0 ? (
          <Alert severity="info" sx={{ mt: 1.5 }}>
            Aucune entreprise importée pour l’instant.
          </Alert>
        ) : (
          <Box sx={{ mt: 0.5 }}>
            <EntreprisesListTable
              rows={entreprises}
              selectedIds={selectedIds}
              onToggleSelected={toggleSelected}
              onToggleSelectAll={toggleSelectAll}
              onApplyCityFilter={applyCityFilter}
              onApplyCategoryFilter={applyCategoryFilter}
              onOpenDetails={handleOpenDetails}
              onDeleteRow={handleDeleteOne}
            />
          </Box>
        )}
        </CardContent>
      </Card>

      <EntrepriseDetailsDialog
        open={detailsOpen}
        entreprise={detailsEntreprise}
        tab={detailsTab}
        onTabChange={setDetailsTab}
        callStats={callStats}
        onClose={() => setDetailsOpen(false)}
      />
    </AppLayout>
  );
}

