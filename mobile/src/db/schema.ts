/**
 * Schema SQLite local VocalGuard mobile.
 */

export const SCHEMA_VERSION = 4;

/** Colonnes voicemails v2 (migration legere). */
export const MIGRATION_V2_STATEMENTS: string[] = [
  "ALTER TABLE voicemails ADD COLUMN caller_name TEXT",
  "ALTER TABLE voicemails ADD COLUMN transcription TEXT",
];

/** Colonnes calls v3 : audio, transcription, OSINT offline. */
export const MIGRATION_V3_STATEMENTS: string[] = [
  "ALTER TABLE calls ADD COLUMN audio_file TEXT",
  "ALTER TABLE calls ADD COLUMN transcription TEXT",
  "ALTER TABLE calls ADD COLUMN no_message INTEGER DEFAULT 0",
  "ALTER TABLE calls ADD COLUMN osint_json TEXT",
];

/** Colonnes calls v4 : cues karaoke offline. */
export const MIGRATION_V4_STATEMENTS: string[] = [
  "ALTER TABLE calls ADD COLUMN transcription_cues_json TEXT",
];

/**
 * Statements DDL v1 (un par un : evite les NPE Android sur execAsync multi-statements).
 */
export const MIGRATION_V1_STATEMENTS: string[] = [
  `CREATE TABLE IF NOT EXISTS calls (
  id INTEGER PRIMARY KEY,
  phone_number TEXT NOT NULL,
  caller_name TEXT,
  status TEXT,
  call_time TEXT,
  duration INTEGER DEFAULT 0,
  synced_at TEXT
)`,
  `CREATE TABLE IF NOT EXISTS voicemails (
  id INTEGER PRIMARY KEY,
  caller_number TEXT NOT NULL,
  duration INTEGER DEFAULT 0,
  is_read INTEGER DEFAULT 0,
  recorded_at TEXT,
  audio_local_path TEXT,
  synced_at TEXT
)`,
  `CREATE TABLE IF NOT EXISTS sync_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  last_sync_at TEXT,
  server_url TEXT,
  pending_count INTEGER DEFAULT 0
)`,
  `CREATE TABLE IF NOT EXISTS pending_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  retry_count INTEGER DEFAULT 0
)`,
  `CREATE TABLE IF NOT EXISTS trusted_contacts (
  phone_number TEXT PRIMARY KEY,
  display_name TEXT,
  device_contact_id TEXT,
  synced_at TEXT,
  is_whitelisted INTEGER DEFAULT 1
)`,
  `INSERT OR IGNORE INTO sync_state (id, last_sync_at, server_url, pending_count)
VALUES (1, NULL, NULL, 0)`,
];

/** Requetes DDL initiales (concat pour tests / compat). */
export const MIGRATION_V1 = MIGRATION_V1_STATEMENTS.join(";\n") + ";";

/** Profil OSINT leger stocke en JSON dans calls.osint_json. */
export interface CallOsintLite {
  phone_number?: string;
  reputation?: string;
  recommendation?: string;
  is_spam?: boolean;
  is_scam?: boolean;
  operator?: string | null;
  city?: string | null;
  region?: string | null;
  is_company?: boolean;
  name?: string | null;
  company_name?: string | null;
}

export interface CallRow {
  id: number;
  phone_number: string;
  caller_name: string | null;
  status: string | null;
  call_time: string | null;
  duration: number;
  synced_at: string | null;
  audio_file?: string | null;
  transcription?: string | null;
  transcription_cues_json?: string | null;
  no_message?: number;
  osint_json?: string | null;
}

export interface VoicemailRow {
  id: number;
  caller_number: string;
  caller_name: string | null;
  transcription: string | null;
  duration: number;
  is_read: number;
  recorded_at: string | null;
  audio_local_path: string | null;
  synced_at: string | null;
}

export interface PendingActionRow {
  id: number;
  action: string;
  payload: string;
  created_at: string;
  retry_count: number;
}

/**
 * Parse le JSON OSINT stocke localement.
 *
 * @param raw Texte JSON ou null.
 * @returns Profil ou null.
 */
export function parseCallOsint(raw: string | null | undefined): CallOsintLite | null {
  if (!raw) return null;
  try {
    const data = JSON.parse(raw) as CallOsintLite;
    if (!data || typeof data !== "object") return null;
    return data;
  } catch {
    return null;
  }
}

/**
 * Parse les cues karaoke stockes en JSON local.
 *
 * @param raw Texte JSON ou null.
 * @returns Tableau brut ou null.
 */
export function parseCallCuesJson(raw: string | null | undefined): unknown[] | null {
  if (!raw) return null;
  try {
    const data = JSON.parse(raw) as unknown;
    if (!Array.isArray(data) || data.length === 0) return null;
    return data;
  } catch {
    return null;
  }
}
