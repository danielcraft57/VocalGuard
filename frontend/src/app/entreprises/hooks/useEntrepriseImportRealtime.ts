import { useEffect } from "react";
import { getApiBaseUrl } from "../../../services/httpClient";
import type { ImportProgressCounters } from "../types";

export function useEntrepriseImportRealtime(opts: {
  activeBatchId?: number | null;
  onProgress: (progressPercent: number | null, counters: ImportProgressCounters | null) => void;
  onCompleted: () => void;
  onOsintEvent?: (payload: { type: "osint.profile.completed" | "osint.profile.failed"; data?: any }) => void;
}) {
  const { activeBatchId, onProgress, onCompleted, onOsintEvent } = opts;

  useEffect(() => {
    const apiBase = getApiBaseUrl();
    const wsBase = apiBase.replace(/^http/, "ws").replace(/\/api\/v1$/, "");
    const wsUrl = `${wsBase}/ws/events`;

    let ws: WebSocket | null = null;
    let pingTimer: number | null = null;
    let pollTimer: number | null = null;
    let disposed = false;
    let currentBatchId: number | null = activeBatchId ?? null;
    let completed = false;

    const syncBatchSummary = async (batchId: number) => {
      try {
        const res = await fetch(`${apiBase}/entreprises/import-batches/${batchId}`);
        if (!res.ok) return;
        const summary = (await res.json()) as {
          total_rows: number;
          imported_rows: number;
          skipped_with_website: number;
          skipped_invalid: number;
          skipped_duplicates: number;
        };

        const total = Number(summary.total_rows ?? 0);
        const imported = Number(summary.imported_rows ?? 0);
        const skippedWebsite = Number(summary.skipped_with_website ?? 0);
        const skippedInvalid = Number(summary.skipped_invalid ?? 0);
        const skippedDuplicates = Number(summary.skipped_duplicates ?? 0);
        const processed = imported + skippedWebsite + skippedInvalid + skippedDuplicates;
        const pct = total > 0 ? Math.min(100, Math.max(0, Math.round((processed / total) * 100))) : null;

        onProgress(pct, { imported, skippedWebsite, skippedInvalid, skippedDuplicates });
        if (!completed && total > 0 && processed >= total) {
          completed = true;
          onProgress(100, null);
          onCompleted();
        }
      } catch {
        // ignore
      }
    };

    try {
      ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        if (disposed) {
          try {
            ws?.close();
          } catch {
            // ignore
          }
          return;
        }
        pingTimer = window.setInterval(() => {
          try {
            ws?.send("ping");
          } catch {
            // ignore
          }
        }, 15000);
        if (currentBatchId && !completed) {
          void syncBatchSummary(currentBatchId);
        }
      };

      ws.onmessage = (evt) => {
        try {
          const payload = JSON.parse(evt.data) as { type?: string; data?: any };
          if (!payload?.type) return;

          if (payload.type === "entreprise.import.started") {
            currentBatchId = Number(payload.data?.batch_id ?? 0) || null;
            completed = false;
          }

          if (payload.type === "entreprise.import.progress") {
            currentBatchId = Number(payload.data?.batch_id ?? 0) || currentBatchId;
            const current = Number(payload.data?.current ?? 0);
            const total = Number(payload.data?.total_rows ?? 0);
            const pct = total > 0 ? Math.min(100, Math.max(0, Math.round((current / total) * 100))) : null;
            onProgress(pct, {
              imported: Number(payload.data?.imported_rows ?? 0),
              skippedWebsite: Number(payload.data?.skipped_with_website ?? 0),
              skippedInvalid: Number(payload.data?.skipped_invalid ?? 0),
              skippedDuplicates: Number(payload.data?.skipped_duplicates ?? 0),
            });
          }

          if (payload.type === "entreprise.import.completed") {
            currentBatchId = Number(payload.data?.batch_id ?? 0) || currentBatchId;
            completed = true;
            onProgress(100, null);
            onCompleted();
          }

          if (payload.type === "osint.profile.completed" || payload.type === "osint.profile.failed") {
            onOsintEvent?.({ type: payload.type, data: payload.data });
          }
        } catch {
          // ignore
        }
      };
    } catch {
      // ignore
    }

    pollTimer = window.setInterval(() => {
      if (!completed && currentBatchId) {
        void syncBatchSummary(currentBatchId);
      }
    }, 2500);

    return () => {
      disposed = true;
      if (pingTimer) window.clearInterval(pingTimer);
      if (pollTimer) window.clearInterval(pollTimer);
      try {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
      } catch {
        // ignore
      }
    };
  }, [activeBatchId, onCompleted, onOsintEvent, onProgress]);
}

