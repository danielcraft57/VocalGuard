/**
 * Moteur de synchronisation offline SQLite.
 */
import type { SqlDb } from "../db/client";
import { apiGet, ApiConfig, SyncDeltaResponse } from "./api";
import { log } from "./log";

/**
 * Applique le delta serveur dans SQLite local.
 *
 * @param db Base locale.
 * @param delta Reponse /public/sync/delta.
 */
export async function applySyncDelta(db: SqlDb, delta: SyncDeltaResponse): Promise<number> {
  const now = new Date().toISOString();
  let count = 0;
  for (const call of delta.calls ?? []) {
    await db.runAsync(
      `INSERT OR REPLACE INTO calls (id, phone_number, caller_name, status, call_time, duration, synced_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        Number(call.id),
        String(call.phone_number ?? ""),
        (call.caller_name as string | null) ?? null,
        (call.status as string | null) ?? null,
        (call.call_time as string | null) ?? null,
        Number(call.duration ?? 0),
        now,
      ],
    );
    count += 1;
  }
  for (const vm of delta.voicemails ?? []) {
    const phone = String(vm.phone_number ?? vm.caller_number ?? vm.caller_phone ?? "");
    const recordedAt = (vm.created_at as string | null) ?? (vm.recorded_at as string | null) ?? null;
    await db.runAsync(
      `INSERT OR REPLACE INTO voicemails (id, caller_number, caller_name, transcription, duration, is_read, recorded_at, audio_local_path, synced_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        Number(vm.id),
        phone,
        (vm.caller_name as string | null) ?? null,
        (vm.transcription as string | null) ?? null,
        Number(vm.duration ?? 0),
        vm.is_read ? 1 : 0,
        recordedAt,
        null,
        now,
      ],
    );
    count += 1;
  }
  return count;
}

/**
 * Pull delta depuis le serveur et merge local.
 *
 * @param db Base SQLite.
 * @param config API Bearer.
 * @param since Horodatage ISO8601 ou null pour full sync.
 */
export async function syncFromServer(db: SqlDb, config: ApiConfig, since: string | null): Promise<number> {
  const qs = since ? `?since=${encodeURIComponent(since)}` : "";
  const path = `/public/sync/delta${qs}`;
  log.debug("sync", "pull delta", { path, since });
  const delta = await apiGet<SyncDeltaResponse>(config, path);
  const merged = await applySyncDelta(db, delta);
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
