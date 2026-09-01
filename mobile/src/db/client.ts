/**
 * Types et mock memoire SQLite (tests + web dev).
 */
import { MIGRATION_V1, MIGRATION_V1_STATEMENTS, MIGRATION_V2_STATEMENTS } from "./schema";

export type SqlDb = {
  execAsync: (sql: string) => Promise<void>;
  runAsync: (sql: string, params?: unknown[]) => Promise<{ changes: number; lastInsertRowId: number }>;
  getAllAsync: <T>(sql: string, params?: unknown[]) => Promise<T[]>;
  getFirstAsync: <T>(sql: string, params?: unknown[]) => Promise<T | null>;
};

let memoryDb: Map<string, unknown[]> | null = null;

type PendingRow = { id: number; action: string; payload: string; created_at: string; retry_count: number };
type SyncRow = { id: number; last_sync_at: string | null; server_url: string | null; pending_count: number };
type CallMem = {
  id: number;
  phone_number: string;
  caller_name: string | null;
  status: string | null;
  call_time: string | null;
  duration: number;
  synced_at: string | null;
};
type VoicemailMem = {
  id: number;
  caller_number: string;
  caller_name: string | null;
  transcription: string | null;
  duration: number;
  is_read: number;
  recorded_at: string | null;
  audio_local_path: string | null;
  synced_at: string | null;
};

/**
 * Initialise une base memoire simplifiee (Jest / navigateur web).
 *
 * @returns Instance DB mock.
 */
export function createMemoryDb(): SqlDb {
  memoryDb = new Map();
  const tables = ["calls", "voicemails", "sync_state", "pending_actions", "trusted_contacts"];
  for (const t of tables) memoryDb.set(t, []);

  const db: SqlDb = {
    async execAsync(sql: string) {
      if (sql.includes("CREATE TABLE")) return;
      if (sql.includes("INSERT OR IGNORE INTO sync_state")) {
        const rows = memoryDb!.get("sync_state") as unknown[];
        if (rows.length === 0) rows.push({ id: 1, last_sync_at: null, server_url: null, pending_count: 0 });
      }
    },
    async runAsync(sql: string, params: unknown[] = []) {
      if (sql.includes("DELETE FROM pending_actions")) {
        const rows = memoryDb!.get("pending_actions") as PendingRow[];
        const id = Number(params[0]);
        const idx = rows.findIndex((r) => r.id === id);
        if (idx >= 0) rows.splice(idx, 1);
        return { changes: 1, lastInsertRowId: 0 };
      }
      if (sql.includes("INSERT INTO pending_actions")) {
        const rows = memoryDb!.get("pending_actions") as PendingRow[];
        const id = rows.length + 1;
        rows.push({
          id,
          action: String(params[0]),
          payload: String(params[1]),
          created_at: String(params[2]),
          retry_count: Number(params[3] ?? 0),
        });
        return { changes: 1, lastInsertRowId: id };
      }
      if (sql.includes("UPDATE sync_state")) {
        const rows = memoryDb!.get("sync_state") as SyncRow[];
        if (rows[0]) {
          if (sql.includes("last_sync_at")) {
            rows[0].last_sync_at = String(params[0]);
            rows[0].pending_count = Number(params[1]);
          } else {
            rows[0].pending_count = Number(params[0]);
          }
        }
        return { changes: 1, lastInsertRowId: 0 };
      }
      if (sql.includes("INSERT OR REPLACE INTO calls")) {
        const rows = memoryDb!.get("calls") as CallMem[];
        const row: CallMem = {
          id: Number(params[0]),
          phone_number: String(params[1]),
          caller_name: params[2] as string | null,
          status: params[3] as string | null,
          call_time: params[4] as string | null,
          duration: Number(params[5]),
          synced_at: String(params[6]),
        };
        const idx = rows.findIndex((r) => r.id === row.id);
        if (idx >= 0) rows[idx] = row;
        else rows.push(row);
        return { changes: 1, lastInsertRowId: row.id };
      }
      if (sql.includes("INSERT OR REPLACE INTO voicemails")) {
        const rows = memoryDb!.get("voicemails") as VoicemailMem[];
        const row: VoicemailMem = {
          id: Number(params[0]),
          caller_number: String(params[1]),
          caller_name: (params[2] as string | null) ?? null,
          transcription: (params[3] as string | null) ?? null,
          duration: Number(params[4]),
          is_read: Number(params[5]),
          recorded_at: params[6] as string | null,
          audio_local_path: params[7] as string | null,
          synced_at: String(params[8]),
        };
        const idx = rows.findIndex((r) => r.id === row.id);
        if (idx >= 0) rows[idx] = row;
        else rows.push(row);
        return { changes: 1, lastInsertRowId: row.id };
      }
      return { changes: 0, lastInsertRowId: 0 };
    },
    async getAllAsync<T>(sql: string, _params: unknown[] = []) {
      if (sql.includes("FROM pending_actions")) {
        return (memoryDb!.get("pending_actions") ?? []) as T[];
      }
      if (sql.includes("FROM calls")) {
        return (memoryDb!.get("calls") ?? []) as T[];
      }
      if (sql.includes("FROM voicemails")) {
        return (memoryDb!.get("voicemails") ?? []) as T[];
      }
      return [] as T[];
    },
    async getFirstAsync<T>(sql: string) {
      if (sql.includes("FROM sync_state")) {
        const rows = memoryDb!.get("sync_state") as T[];
        return rows[0] ?? null;
      }
      return null;
    },
  };

  void db.execAsync(MIGRATION_V1);
  return db;
}

/**
 * Applique les migrations sur une DB SQLite (expo ou memoire).
 *
 * @param db Instance SQL.
 */
export async function migrateDb(db: SqlDb): Promise<void> {
  for (const statement of MIGRATION_V1_STATEMENTS) {
    await db.execAsync(statement);
  }
  for (const statement of MIGRATION_V2_STATEMENTS) {
    try {
      await db.execAsync(statement);
    } catch {
      /* colonne deja presente */
    }
  }
}
