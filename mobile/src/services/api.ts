import { log } from "./log";
import { invalidateMobileSession } from "./session";

export interface ApiConfig {
  baseUrl: string;
  token: string;
}

export class ApiHttpError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiHttpError";
    this.status = status;
  }
}

/**
 * Indique si l erreur est un 401 (token invalide / expire).
 */
export function isApiUnauthorized(err: unknown): boolean {
  return err instanceof ApiHttpError && err.status === 401;
}

async function handleFailedResponse(method: string, path: string, res: Response): Promise<never> {
  log.warn("api", `${method} ${path} -> ${res.status}`);
  if (res.status === 401) {
    void invalidateMobileSession(`${method} ${path}`);
  }
  throw new ApiHttpError(res.status, `API ${method} ${path} -> ${res.status}`);
}

export interface SyncDeltaResponse {
  calls?: Array<Record<string, unknown>>;
  voicemails?: Array<Record<string, unknown>>;
  server_time?: string;
}

const DEFAULT_TIMEOUT_MS = 15000;

/**
 * Fetch avec timeout (evite "Synchronisation en cours" bloque pour toujours).
 *
 * @param url URL.
 * @param init Options fetch.
 * @param timeoutMs Delai max.
 */
async function fetchWithTimeout(url: string, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Construit l URL API complete.
 *
 * @param baseUrl URL nginx (sans /api/v1).
 * @param path Chemin relatif public.
 */
export function buildApiUrl(baseUrl: string, path: string): string {
  const root = baseUrl.replace(/\/$/, "");
  const suffix = path.startsWith("/") ? path : `/${path}`;
  if (root.endsWith("/api/v1")) return `${root}${suffix}`;
  return `${root}/api/v1${suffix}`;
}

/**
 * Effectue une requete GET authentifiee.
 *
 * @param config Configuration API.
 * @param path Chemin sous /api/v1/public.
 */
export async function apiGet<T>(config: ApiConfig, path: string): Promise<T> {
  const url = buildApiUrl(config.baseUrl, path);
  log.debug("api", "GET", { path });
  const res = await fetchWithTimeout(url, {
    headers: { Authorization: `Bearer ${config.token}` },
  });
  if (!res.ok) {
    await handleFailedResponse("GET", path, res);
  }
  return (await res.json()) as T;
}

/**
 * Effectue une requete POST authentifiee.
 *
 * @param config Configuration API.
 * @param path Chemin sous /api/v1/public.
 * @param body Corps JSON.
 */
export async function apiPost<T>(config: ApiConfig, path: string, body: unknown): Promise<T> {
  const url = buildApiUrl(config.baseUrl, path);
  log.debug("api", "POST", { path });
  const res = await fetchWithTimeout(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${config.token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    await handleFailedResponse("POST", path, res);
  }
  return (await res.json()) as T;
}

/**
 * Effectue une requete DELETE authentifiee.
 *
 * @param config Configuration API.
 * @param path Chemin sous /api/v1/public.
 */
export async function apiDelete<T = { ok: boolean }>(config: ApiConfig, path: string): Promise<T> {
  const url = buildApiUrl(config.baseUrl, path);
  log.debug("api", "DELETE", { path });
  const res = await fetchWithTimeout(url, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${config.token}` },
  });
  if (!res.ok) {
    await handleFailedResponse("DELETE", path, res);
  }
  return (await res.json()) as T;
}

/**
 * Ping connexion mobile securise.
 *
 * @param config Configuration API.
 */
export async function pingMobile(config: ApiConfig): Promise<{ ok: boolean; ws_ok: boolean }> {
  const data = await apiGet<{ ok: boolean; ws_ok: boolean }>(config, "/public/mobile/ping");
  return data;
}

/**
 * Claim appairage QR.
 *
 * @param baseUrl URL serveur sans token.
 * @param code Code 8 caracteres.
 */
export async function claimPairing(
  baseUrl: string,
  code: string,
): Promise<{ token: string; base_url: string; permissions: Record<string, boolean> }> {
  const url = buildApiUrl(baseUrl, "/public/mobile/claim");
  log.info("api", "claim pairing", { baseUrl, codeLen: code.length });
  const res = await fetchWithTimeout(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: code.toUpperCase(), device_hint: "expo" }),
  });
  if (!res.ok) {
    let extra = `${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) extra = body.detail;
    } catch {
      /* ignore */
    }
    log.warn("api", "claim failed", { extra });
    throw new Error(`Claim echoue: ${extra}`);
  }
  log.info("api", "claim ok");
  return (await res.json()) as { token: string; base_url: string; permissions: Record<string, boolean> };
}
