/**
 * Gestion des personnes de confiance (whitelist).
 */
import type { SqlDb } from "../db/client";
import { apiDelete, apiGet, ApiConfig } from "./api";

export interface TrustedContact {
  phone_number: string;
  name: string | null;
  updated_at: string | null;
}

interface TrustedListResponse {
  trusted: Array<{
    phone_number: string;
    name?: string | null;
    updated_at?: string | null;
  }>;
}

/**
 * Recupere la liste des personnes de confiance depuis l API.
 *
 * @param config Configuration API Bearer.
 */
export async function fetchTrustedList(config: ApiConfig): Promise<TrustedContact[]> {
  const data = await apiGet<TrustedListResponse>(config, "/public/trusted");
  return (data.trusted ?? []).map((row) => ({
    phone_number: row.phone_number,
    name: row.name ?? null,
    updated_at: row.updated_at ?? null,
  }));
}

/**
 * Retire un numero de la liste blanche.
 *
 * @param config Configuration API Bearer.
 * @param phone Numero normalise.
 */
export async function removeTrustedContact(config: ApiConfig, phone: string): Promise<void> {
  await apiDelete(config, `/public/trusted/${encodeURIComponent(phone)}`);
}

/**
 * Met en cache localement les contacts de confiance.
 *
 * @param db Base SQLite.
 * @param contacts Liste serveur.
 */
export async function cacheTrustedContacts(db: SqlDb, contacts: TrustedContact[]): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync("DELETE FROM trusted_contacts");
  for (const c of contacts) {
    await db.runAsync(
      `INSERT OR REPLACE INTO trusted_contacts (phone_number, display_name, synced_at, is_whitelisted)
       VALUES (?, ?, ?, 1)`,
      [c.phone_number, c.name, now],
    );
  }
}

/**
 * Charge le cache local des personnes de confiance.
 *
 * @param db Base SQLite.
 */
export async function loadTrustedFromCache(db: SqlDb): Promise<TrustedContact[]> {
  const rows = await db.getAllAsync<{ phone_number: string; display_name: string | null }>(
    "SELECT phone_number, display_name FROM trusted_contacts WHERE is_whitelisted = 1 ORDER BY display_name",
  );
  return rows.map((r) => ({
    phone_number: r.phone_number,
    name: r.display_name,
    updated_at: null,
  }));
}
