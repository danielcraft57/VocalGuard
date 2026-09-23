/**
 * Moteur de synchronisation offline SQLite.
 */
import type { SqlDb } from "../db/client";
import { apiGet, ApiConfig, SyncDeltaResponse } from "./api";
import { log } from "./log";

/** Aligne sur le lookback appels du delta public (7 j). */
export const CALL_SYNC_LOOKBACK_DAYS = 7;

/** Aligne sur le lookback messages du delta public (72 h). */
export const VM_SYNC_LOOKBACK_HOURS = 72;

/**
 * Serialise le bloc OSINT du delta en JSON local.
 *
 * @param osint Objet OSINT ou null.
 * @returns Chaine JSON ou null.
 */
function serializeOsint(osint: unknown): string | null {
  if (!osint || typeof osint !== "object") return null;
  try {
    return JSON.stringify(osint);
  } catch {
    return null;
  }
}

/**
 * Garde l OSINT le plus riche entre incoming et cache local.
 *
 * @param incoming JSON OSINT du delta (ou null).
 * @param existing JSON deja en base locale.
 * @returns JSON a persister.
 */
function preferOsintJson(incoming: string | null, existing: string | null): string | null {
  if (!incoming) return existing;
  if (!existing) return incoming;
  try {
    const a = JSON.parse(incoming) as Record<string, unknown>;
    const b = JSON.parse(existing) as Record<string, unknown>;
    const score = (o: Record<string, unknown>) =>
      [o.operator, o.carrier, o.company_name, o.name, o.city, o.reputation].filter(
        (v) => typeof v === "string" && v.trim().length > 0,
      ).length;
    return score(a) >= score(b) ? incoming : existing;
  } catch {
    return incoming;
  }
}

/**
 * Serialise les cues karaoke du delta.
 *
 * @param cues Tableau cues ou null.
 * @returns Chaine JSON ou null.
 */
function serializeCues(cues: unknown): string | null {
  if (!Array.isArray(cues) || cues.length === 0) return null;
  try {
    return JSON.stringify(cues);
  } catch {
    return null;
  }
}

type ApplySyncOptions = {
  /** Purge les appels hors fenetre / absents du delta (sync fenetre complete). */
  pruneCalls?: boolean;
  /** Purge les messages hors fenetre / absents du delta. */
  pruneVoicemails?: boolean;
};

/**
 * Supprime les lignes locales hors fenetre, et celles absentes du delta serveur.
 *
 * @param db Base locale.
 * @param table Nom table.
 * @param timeColumn Colonne horodatage ISO.
 * @param cutoffIso Borne basse ISO.
 * @param keepIds Ids renvoyes par le serveur (fenetre complete).
 * @returns Nombre de suppressions.
 */
async function pruneTableByWindow(
  db: SqlDb,
  table: "calls" | "voicemails",
  timeColumn: "call_time" | "recorded_at",
  cutoffIso: string,
  keepIds: number[] | null,
): Promise<number> {
  let removed = 0;
  const stale = await db.getAllAsync<{ id: number }>(
    `SELECT id FROM ${table} WHERE ${timeColumn} IS NULL OR ${timeColumn} < ?`,
    [cutoffIso],
  );
  for (const row of stale) {
    await db.runAsync(`DELETE FROM ${table} WHERE id = ?`, [row.id]);
    removed += 1;
  }
  if (keepIds == null) return removed;
  const keep = new Set(keepIds);
  const recent = await db.getAllAsync<{ id: number }>(
    `SELECT id FROM ${table} WHERE ${timeColumn} >= ?`,
    [cutoffIso],
  );
  for (const row of recent) {
    if (!keep.has(row.id)) {
      await db.runAsync(`DELETE FROM ${table} WHERE id = ?`, [row.id]);
      removed += 1;
    }
  }
  return removed;
}

/**
 * Applique le delta serveur dans SQLite local.
 *
 * @param db Base locale.
 * @param delta Reponse /public/sync/delta.
 * @param options Options de purge cache.
 */
export async function applySyncDelta(
  db: SqlDb,
  delta: SyncDeltaResponse,
  options: ApplySyncOptions = {},
): Promise<number> {
  const now = new Date().toISOString();
  const nowMs = Date.now();
  let count = 0;
  for (const call of delta.calls ?? []) {
    const callId = Number(call.id);
    const existing = await db.getFirstAsync<{
      transcription: string | null;
      transcription_cues_json: string | null;
      osint_json: string | null;
    }>("SELECT transcription, transcription_cues_json, osint_json FROM calls WHERE id = ?", [callId]);

    const incomingTranscription = ((call.transcription as string | null) ?? "").trim() || null;
    const transcription = incomingTranscription ?? existing?.transcription ?? null;
    const incomingCues = serializeCues(call.transcription_cues);
    const cuesJson = incomingCues ?? existing?.transcription_cues_json ?? null;
    const incomingOsint = serializeOsint(call.osint);
    const osintJson = preferOsintJson(incomingOsint, existing?.osint_json ?? null);

    await db.runAsync(
      `INSERT OR REPLACE INTO calls (
        id, phone_number, caller_name, status, call_time, duration, synced_at,
        audio_file, transcription, no_message, osint_json, transcription_cues_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        callId,
        String(call.phone_number ?? ""),
        (call.caller_name as string | null) ?? null,
        (call.status as string | null) ?? null,
        (call.call_time as string | null) ?? null,
        Number(call.duration ?? 0),
        now,
        (call.audio_file as string | null) ?? null,
        transcription,
        call.no_message ? 1 : 0,
        osintJson,
        cuesJson,
      ],
    );
    count += 1;
  }
  for (const vm of delta.voicemails ?? []) {
    const vmId = Number(vm.id);
    const incomingPhone = String(vm.phone_number ?? vm.caller_number ?? vm.caller_phone ?? "").trim();
    const incomingName = ((vm.caller_name as string | null) ?? "").trim() || null;
    const existing = await db.getFirstAsync<{
      caller_number: string;
      caller_name: string | null;
      transcription: string | null;
      audio_local_path: string | null;
    }>("SELECT caller_number, caller_name, transcription, audio_local_path FROM voicemails WHERE id = ?", [
      vmId,
    ]);
    const callerNumber = incomingPhone || existing?.caller_number?.trim() || "";
    const callerName = incomingName ?? existing?.caller_name ?? null;
    const incomingTranscription = ((vm.transcription as string | null) ?? "").trim() || null;
    const transcription = incomingTranscription ?? existing?.transcription ?? null;
    const recordedAt = (vm.created_at as string | null) ?? (vm.recorded_at as string | null) ?? null;
    await db.runAsync(
      `INSERT OR REPLACE INTO voicemails (id, caller_number, caller_name, transcription, duration, is_read, recorded_at, audio_local_path, synced_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        vmId,
        callerNumber,
        callerName,
        transcription,
        Number(vm.duration ?? 0),
        vm.is_read ? 1 : 0,
        recordedAt,
        existing?.audio_local_path ?? null,
        now,
      ],
    );
    count += 1;
  }

  if (options.pruneCalls) {
    const cutoff = new Date(nowMs - CALL_SYNC_LOOKBACK_DAYS * 24 * 60 * 60 * 1000).toISOString();
    const keepIds = (delta.calls ?? []).map((c) => Number(c.id)).filter((id) => Number.isFinite(id));
    const removed = await pruneTableByWindow(db, "calls", "call_time", cutoff, keepIds);
    if (removed > 0) log.info("sync", "appels purges du cache local", { removed });
  }
  if (options.pruneVoicemails) {
    const cutoff = new Date(nowMs - VM_SYNC_LOOKBACK_HOURS * 60 * 60 * 1000).toISOString();
    const keepIds = (delta.voicemails ?? []).map((v) => Number(v.id)).filter((id) => Number.isFinite(id));
    const removed = await pruneTableByWindow(db, "voicemails", "recorded_at", cutoff, keepIds);
    if (removed > 0) log.info("sync", "messages purges du cache local", { removed });
  }

  return count;
}

/**
 * Pull delta depuis le serveur et merge local.
 *
 * @param db Base SQLite.
 * @param config API Bearer.
 * @param since Horodatage ISO8601 ou null pour fenetre complete (+ purge cache).
 */
export async function syncFromServer(db: SqlDb, config: ApiConfig, since: string | null): Promise<number> {
  const qs = since ? `?since=${encodeURIComponent(since)}` : "";
  const path = `/public/sync/delta${qs}`;
  log.debug("sync", "pull delta", { path, since });
  const delta = await apiGet<SyncDeltaResponse>(config, path);
  const fullWindow = !since;
  const merged = await applySyncDelta(db, delta, {
    pruneCalls: fullWindow,
    pruneVoicemails: fullWindow,
  });
  const pending = await db.getAllAsync<{ id: number }>("SELECT id FROM pending_actions ORDER BY id ASC");
  const serverTime = delta.server_time ?? new Date().toISOString();
  await db.runAsync("UPDATE sync_state SET last_sync_at = ?, pending_count = ? WHERE id = 1", [
    serverTime,
    pending.length,
  ]);
  log.info("sync", "delta applique", {
    merged,
    pending: pending.length,
    serverTime,
    calls: delta.calls?.length ?? 0,
    voicemails: delta.voicemails?.length ?? 0,
    pruned: fullWindow,
  });
  return merged;
}

/**
 * Rejoue la file pending_actions (mark_read, trusted_import, ...).
 *
 * @param db Base SQLite.
 * @param executor Fonction qui execute une action cote API.
 */
export async function replayPendingActions(
  db: SqlDb,
  executor: (action: string, payload: Record<string, unknown>) => Promise<void>,
): Promise<number> {
  const rows = await db.getAllAsync<{ id: number; action: string; payload: string }>(
    "SELECT id, action, payload FROM pending_actions ORDER BY id ASC",
  );
  let done = 0;
  for (const row of rows) {
    const payload = JSON.parse(row.payload) as Record<string, unknown>;
    await executor(row.action, payload);
    await db.runAsync("DELETE FROM pending_actions WHERE id = ?", [row.id]);
    done += 1;
  }
  return done;
}

/**
 * Enqueue une action offline.
 *
 * @param db Base SQLite.
 * @param action Nom action.
 * @param payload Donnees JSON serialisables.
 */
export async function enqueuePendingAction(
  db: SqlDb,
  action: string,
  payload: Record<string, unknown>,
): Promise<void> {
  await db.runAsync(
    "INSERT INTO pending_actions (action, payload, created_at, retry_count) VALUES (?, ?, ?, 0)",
    [action, JSON.stringify(payload), new Date().toISOString()],
  );
  const pending = await db.getAllAsync<{ id: number }>("SELECT id FROM pending_actions");
  await db.runAsync("UPDATE sync_state SET pending_count = ? WHERE id = 1", [pending.length]);
}
