/**
 * Retourne l'URL de base de l'API VocalGuard.
 *
 * - Cote navigateur : on utilise un chemin relatif /api/v1 pour que les appels
 *   soient same-origin quand le front est servi par le backend (pas de CORS, vraies donnees).
 * - Cote build (Node) : on utilise la variable d'env ou localhost pour le fallback.
 *
 * @returns URL de base de l'API.
 */
export function getApiBaseUrl(): string {
  const envBase = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").trim();
  if (envBase) {
    return envBase;
  }

  if (typeof window !== "undefined") {
    // En dev Next.js (localhost:3000), l'API FastAPI tourne sur :8000.
    if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
      return `${window.location.protocol}//${window.location.hostname}:8000/api/v1`;
    }
    // En mode "front servi par le backend", on garde le same-origin.
    return "/api/v1";
  }
  return "http://localhost:8000/api/v1";
}

/**
 * Base WebSocket (sans chemin) alignee sur l'API pour /ws/events et /ws/outgoing-call/...
 */
export function getWsBaseUrl(): string {
  const envBase = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").trim();
  if (envBase) {
    const trimmed = envBase.replace(/\/api\/v1\/?$/, "").replace(/\/$/, "");
    return trimmed.replace(/^http/, "ws");
  }
  if (typeof window !== "undefined") {
    if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
      return `ws://${window.location.hostname}:8000`;
    }
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${window.location.host}`;
  }
  return "ws://localhost:8000";
}

/**
 * WebSocket audio appel sortant : avec USE_TELEPHONY_DAEMON la session vit sur le daemon
 * (ex. node14:8090), pas sur l API locale — definir NEXT_PUBLIC_TELEPHONY_WS_BASE (ex. ws://node14.lan:8090).
 */
export function getOutgoingAudioWsBaseUrl(): string {
  const tel = (process.env.NEXT_PUBLIC_TELEPHONY_WS_BASE ?? "").trim();
  if (tel) {
    let u = tel.replace(/\/$/, "");
    if (u.startsWith("http://")) u = "ws://" + u.slice("http://".length);
    else if (u.startsWith("https://")) u = "wss://" + u.slice("https://".length);
    return u;
  }
  return getWsBaseUrl();
}

/**
 * Helper minimal pour effectuer une requete GET et parser du JSON.
 *
 * @param path Chemin relatif a l'API (ex: /calls).
 * @returns Donnees parsees typées.
 */
export async function getJson<T>(path: string): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}${path}`, { cache: "no-store" });

  if (!res.ok) {
    throw new Error(`Erreur API GET ${path}: ${res.status}`);
  }

  return (await res.json()) as T;
}

