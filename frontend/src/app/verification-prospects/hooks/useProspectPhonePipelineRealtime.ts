import { useEffect, useRef } from "react";
import { getApiBaseUrl, getWsBaseUrl } from "../../../services/httpClient";
import type { ProspectPhone, ProspectPhoneImportSummary } from "../../../services/prospectPhonesApi";

export type PipelinePhase = "idle" | "import" | "enrich" | "done" | "failed";

export type EnrichStep = "start" | "parallel" | "queued" | "done" | "failed";

/** Snapshot prospect envoye par le backend (WS enrich.row). */
export type ProspectEnrichRowPatch = Partial<ProspectPhone> & { id: number };

export interface PipelineState {
  phase: PipelinePhase;
  importSummary: ProspectPhoneImportSummary | null;
  importPercent: number | null;
  enrichPercent: number | null;
  logLine: string | null;
  enrichStep?: EnrichStep | null;
  enrichCurrent?: number | null;
  enrichEngine?: string | null;
  enrichParallel?: number | null;
  activeProspect?: ProspectEnrichRowPatch | null;
  lastProspect?: ProspectEnrichRowPatch | null;
}

/** Phase API batch -> phase UI pipeline. */
export function normalizeBatchPhase(phase: string): PipelinePhase {
  if (phase === "pending") return "import";
  if (phase === "import" || phase === "enrich" || phase === "done" || phase === "failed") {
    return phase as PipelinePhase;
  }
  return "idle";
}

/**
 * Calcule pourcentages et phase a partir du resume batch (reprise apres refresh).
 */
export function pipelinePatchFromImportSummary(summary: ProspectPhoneImportSummary): Partial<PipelineState> {
  const total = summary.total_rows || 0;
  const imported =
    summary.imported_rows +
    summary.skipped_duplicates +
    summary.skipped_invalid +
    summary.skipped_with_website;
  const importPct = total > 0 ? Math.min(100, Math.round((imported / total) * 100)) : null;

  const enrichTotal = summary.enrich_total || 0;
  const enrichDone = (summary.enrich_done || 0) + (summary.enrich_failed || 0);
  const enrichPct = enrichTotal > 0 ? Math.min(100, Math.round((enrichDone / enrichTotal) * 100)) : null;

  const phase = normalizeBatchPhase(summary.phase || "pending");
  return {
    phase,
    importSummary: summary,
    importPercent: importPct,
    enrichPercent: enrichPct,
  };
}

export const IDLE_PIPELINE: PipelineState = {
  phase: "idle",
  importSummary: null,
  importPercent: null,
  enrichPercent: null,
  logLine: null,
  enrichStep: null,
  enrichCurrent: null,
  enrichEngine: null,
  enrichParallel: null,
  activeProspect: null,
  lastProspect: null,
};

function enrichPercentFromPayload(data: Record<string, unknown>): number | null {
  const total = Number(data.enrich_total) || 0;
  if (total <= 0) return null;
  const done = Number(data.enrich_done) || 0;
  const failed = Number(data.enrich_failed) || 0;
  return Math.min(100, Math.round(((done + failed) / total) * 100));
}

function logLineForEnrich(data: Record<string, unknown>): string {
  const step = String(data.step || "");
  const prospect = (data.prospect || {}) as Record<string, unknown>;
  const name = String(prospect.name || "").trim();
  const phone = String(prospect.phone_number || "").trim();
  const label = name ? `${name}${phone ? ` · ${phone}` : ""}` : phone || "numero";
  const current = Number(data.current) || 0;
  const total = Number(data.enrich_total) || 0;
  const progress = total > 0 ? ` (${current}/${total})` : "";

  if (step === "parallel") {
    const par = Number(data.enrich_parallel) || 1;
    const engine = String(data.enrich_engine || "osint");
    return `Analyse en parallele x${par} via ${engine}${progress}`;
  }
  if (step === "start") {
    return `OSINT + ProspectLab en cours : ${label}${progress}`;
  }
  if (step === "queued") {
    return `File async (Celery) : ${label}${progress}`;
  }
  if (step === "done") {
    const pl = String(prospect.prospectlab_status || "");
    const osint = String(prospect.osint_status || "");
    return `Termine : ${label} — OSINT ${osint}, ProspectLab ${pl}${progress}`;
  }
  if (step === "failed") {
    const err = String(data.error || "").trim();
    return err ? `Echec ${label} : ${err}` : `Echec : ${label}${progress}`;
  }
  return "Analyse OSINT / ProspectLab…";
}

/**
 * Suit import XLSX + enrichissement OSINT via WebSocket et polling batch.
 */
export function useProspectPhonePipelineRealtime(opts: {
  /** Lot suivi en direct (import/OSINT). Null = pas de WS ni polling. */
  pipelineBatchId: number | null;
  onState: (patch: Partial<PipelineState>) => void;
  onRefreshList: () => void;
  onProspectRow?: (row: ProspectEnrichRowPatch, step: EnrichStep) => void;
  /** Appele quand tout le lot est termine. */
  onPipelineComplete?: () => void;
}) {
  const { pipelineBatchId, onState, onRefreshList, onProspectRow, onPipelineComplete } = opts;
  const onStateRef = useRef(onState);
  const onRefreshRef = useRef(onRefreshList);
  const onRowRef = useRef(onProspectRow);
  const onCompleteRef = useRef(onPipelineComplete);

  useEffect(() => {
    onStateRef.current = onState;
    onRefreshRef.current = onRefreshList;
    onRowRef.current = onProspectRow;
    onCompleteRef.current = onPipelineComplete;
  }, [onState, onRefreshList, onProspectRow, onPipelineComplete]);

  useEffect(() => {
    if (!pipelineBatchId) return;

    const apiBase = getApiBaseUrl();
    const wsUrl = `${getWsBaseUrl()}/ws/events`;

    let ws: WebSocket | null = null;
    let pollTimer: number | null = null;
    let terminalHandled = false;

    const stopPolling = () => {
      if (pollTimer != null) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    };

    const markTerminal = (patch: Partial<PipelineState>) => {
      if (terminalHandled) return;
      terminalHandled = true;
      onStateRef.current(patch);
      onRefreshRef.current();
      onCompleteRef.current?.();
      stopPolling();
    };

    const syncBatch = async () => {
      try {
        const res = await fetch(`${apiBase}/prospect-phones/import-batches/${pipelineBatchId}`);
        if (!res.ok) return;
        const summary = (await res.json()) as ProspectPhoneImportSummary;
        const patch = pipelinePatchFromImportSummary(summary);
        const phase = patch.phase ?? "idle";

        if (phase === "done" || phase === "failed") {
          markTerminal(patch);
          return;
        }
        if (!terminalHandled) {
          onStateRef.current(patch);
        }
      } catch {
        // ignore
      }
    };

    const applyEnrichPayload = (data: Record<string, unknown>) => {
      const step = String(data.step || "start") as EnrichStep;
      const prospectRaw = data.prospect as Record<string, unknown> | undefined;
      const prospect =
        prospectRaw && prospectRaw.id != null
          ? (prospectRaw as ProspectEnrichRowPatch)
          : null;

      onStateRef.current({
        phase: "enrich",
        enrichPercent: enrichPercentFromPayload(data),
        enrichStep: step,
        enrichCurrent: Number(data.current) || null,
        enrichEngine: (data.enrich_engine as string) || null,
        enrichParallel: Number(data.enrich_parallel) || null,
        logLine: logLineForEnrich(data),
        activeProspect: step === "start" || step === "queued" ? prospect : null,
        lastProspect: step === "done" || step === "failed" ? prospect ?? null : undefined,
      });

      if (prospect && (step === "done" || step === "failed" || step === "start" || step === "queued")) {
        onRowRef.current?.(prospect, step);
      }
      if (step === "done" || step === "failed") {
        onRefreshRef.current();
      }
    };

    const handlePayload = (payload: { type?: string; data?: Record<string, unknown> }) => {
      const data = payload.data || {};
      if (Number(data.batch_id) !== pipelineBatchId) return;

      if (payload.type === "prospect_phone.import.progress") {
        onStateRef.current({ phase: "import", logLine: "Import Excel en cours…" });
        void syncBatch();
      }
      if (payload.type === "prospect_phone.import.completed") {
        onStateRef.current({ phase: "enrich", logLine: "Import termine, lancement OSINT…" });
        void syncBatch();
      }
      if (payload.type === "prospect_phone.enrich.progress") {
        applyEnrichPayload({ ...data, step: data.step || "parallel" });
        void syncBatch();
      }
      if (payload.type === "prospect_phone.enrich.row") {
        applyEnrichPayload(data);
        void syncBatch();
      }
      if (payload.type === "prospect_phone.enrich.completed") {
        markTerminal({
          phase: "done",
          logLine: "Import et analyse termines.",
          activeProspect: null,
        });
        void syncBatch();
      }
      if (payload.type === "prospect_phone.import.failed") {
        onStateRef.current({ phase: "failed", logLine: String(data.error || "Echec import") });
      }
      if (payload.type === "osint.profile.completed" && data.prospect) {
        applyEnrichPayload({ ...data, step: "done" });
      }
    };

    try {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (ev) => {
        try {
          const payload = JSON.parse(String(ev.data)) as { type?: string; data?: Record<string, unknown> };
          handlePayload(payload);
        } catch {
          // ignore
        }
      };
    } catch {
      // ignore
    }

    pollTimer = window.setInterval(() => void syncBatch(), 2000);
    void syncBatch();

    return () => {
      if (pollTimer) window.clearInterval(pollTimer);
      try {
        ws?.close();
      } catch {
        // ignore
      }
    };
  }, [pipelineBatchId]);
}
