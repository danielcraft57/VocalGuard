/**
 * Detection connectivite LAN (ping health nginx).
 */
import { log } from "./log";

export type ConnectivityState = "online" | "offline" | "syncing";

/**
 * Verifie si le serveur VocalGuard repond sur /health.
 *
 * @param baseUrl URL racine (ex. https://node12.lan).
 * @returns True si HTTP 2xx.
 */
export async function pingHealth(baseUrl: string): Promise<boolean> {
  const root = baseUrl.replace(/\/api\/v1\/?$/, "").replace(/\/$/, "");
  if (!root) {
    log.debug("net", "ping saute (url vide)");
    return false;
  }
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const res = await fetch(`${root}/health`, { method: "GET", signal: controller.signal });
      log.debug("net", "ping health", { ok: res.ok, status: res.status });
      return res.ok;
    } finally {
      clearTimeout(timer);
    }
  } catch (err) {
    log.warn("net", "ping health failed", err);
    return false;
  }
}

/**
 * Determine l etat reseau pour l UI.
 *
 * @param baseUrl URL serveur.
 * @param syncing Sync en cours.
 */
export async function resolveConnectivityState(baseUrl: string, syncing = false): Promise<ConnectivityState> {
  if (syncing) return "syncing";
  if (!baseUrl.trim()) return "offline";
  const ok = await pingHealth(baseUrl);
  return ok ? "online" : "offline";
}
