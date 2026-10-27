const PIPELINE_BATCH_KEY = "vg_verif_prospects_active_batch_v1";

/**
 * Retourne l'id du lot d'import en cours (session), ou null.
 */
export function loadPersistedImportBatchId(): number | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(PIPELINE_BATCH_KEY);
    if (!raw) return null;
    const id = Number(raw);
    return Number.isFinite(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

/**
 * Memorise le lot en cours pour retrouver l'avancement apres refresh.
 *
 * @param batchId Identifiant du lot.
 */
export function savePersistedImportBatchId(batchId: number): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(PIPELINE_BATCH_KEY, String(batchId));
  } catch {
    /* ignore quota */
  }
}

/**
 * Efface le lot memorise (pipeline termine ou abandon).
 */
export function clearPersistedImportBatchId(): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.removeItem(PIPELINE_BATCH_KEY);
  } catch {
    /* ignore */
  }
}
