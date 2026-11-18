/**
 * Cache session / memoire pour basculement de pages fluide.
 * Utilise par dashboard, appels, settings, listes, etc.
 */

/** TTL defaut (ms) avant soft-refresh reseau. */
export const UI_CACHE_TTL_MS = 5 * 60 * 1000;

type CacheEntry<T> = {
  data: T;
  savedAt: number;
};

const memory = new Map<string, CacheEntry<unknown>>();

function readSession<T>(key: string): CacheEntry<T> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as CacheEntry<T>;
  } catch {
    return null;
  }
}

function writeSession(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / private mode */
  }
}

/**
 * Lit un cache (memoire puis sessionStorage).
 *
 * @param key Cle unique (ex. vg_cache_stats).
 * @returns Donnees ou null.
 */
export function loadUiCache<T>(key: string): T | null {
  const mem = memory.get(key) as CacheEntry<T> | undefined;
  if (mem && mem.data !== undefined && mem.data !== null) {
    return mem.data;
  }
  const fromSession = readSession<T>(key);
  if (fromSession && fromSession.data !== undefined && fromSession.data !== null) {
    memory.set(key, fromSession as CacheEntry<unknown>);
    return fromSession.data;
  }
  return null;
}

/**
 * Lit le cache avec timestamp (pour TTL).
 *
 * @param key Cle.
 */
export function loadUiCacheEntry<T>(key: string): CacheEntry<T> | null {
  const mem = memory.get(key) as CacheEntry<T> | undefined;
  if (mem) return mem;
  const fromSession = readSession<T>(key);
  if (fromSession) {
    memory.set(key, fromSession as CacheEntry<unknown>);
    return fromSession;
  }
  return null;
}

/**
 * Ecrit le cache.
 *
 * @param key Cle.
 * @param data Payload.
 */
export function saveUiCache<T>(key: string, data: T): void {
  const payload: CacheEntry<T> = { data, savedAt: Date.now() };
  memory.set(key, payload as CacheEntry<unknown>);
  writeSession(key, payload);
}

/**
 * True si le cache est encore frais.
 *
 * @param key Cle.
 * @param ttlMs Duree de vie.
 */
export function isUiCacheFresh(key: string, ttlMs: number = UI_CACHE_TTL_MS): boolean {
  const entry = loadUiCacheEntry(key);
  if (!entry) return false;
  return Date.now() - entry.savedAt < ttlMs;
}

/**
 * True si l'erreur vient d'un AbortController.
 *
 * @param err Erreur catch.
 */
export function isAbortError(err: unknown): boolean {
  if (!err) return false;
  if (typeof DOMException !== "undefined" && err instanceof DOMException) {
    return err.name === "AbortError";
  }
  return (
    typeof err === "object" &&
    err !== null &&
    "name" in err &&
    (err as { name?: string }).name === "AbortError"
  );
}

/** Cles stables partagees entre pages. */
export const UI_CACHE_KEYS = {
  dashboardStats: "vg_cache_dashboard_stats_v1",
  callsOsint: "vg_cache_calls_osint_v1",
  voicemails: "vg_cache_voicemails_v1",
  clients: "vg_cache_clients_v1",
  quotes: "vg_cache_quotes_v1",
  entreprises: "vg_cache_entreprises_v1",
  whitelist: "vg_cache_whitelist_v1",
  blocklist: "vg_cache_blocklist_v1",
  blockRules: "vg_cache_block_rules_v1",
  incomingCallConfig: "vg_cache_incoming_call_config_v1",
  settingsSnapshot: "vg_cache_settings_snapshot_v1",
  telephonyStatus: "vg_cache_telephony_status_v1",
  greetingJingles: "vg_cache_greeting_jingles_v1",
  audioPresets: "vg_cache_audio_presets_v1",
  publicTokens: "vg_cache_public_tokens_v1",
  publicApiDocs: "vg_cache_public_api_docs_v1",
  appointments: "vg_cache_appointments_v1",
  appointmentSettings: "vg_cache_appointment_settings_v1"
} as const;
