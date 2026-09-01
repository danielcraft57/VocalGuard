import { getApiBaseUrl } from "./httpClient";

/** Reponse creation session appairage QR. */
export interface MobilePairingSession {
  pairing_id: number;
  code: string;
  expires_at: string;
  qr_uri: string;
}

/** Resultat ping mobile depuis le serveur. */
export interface MobilePingResult {
  ok: boolean;
  api_ok: boolean;
  ws_ok: boolean;
  modem_ok: boolean;
  permissions: Record<string, boolean>;
}

/**
 * Construit les en-tetes admin tokens (x-admin-token).
 *
 * @returns En-tetes HTTP pour routes /tokens.
 */
function buildAdminHeaders(): HeadersInit {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  let admin = (process.env.NEXT_PUBLIC_PUBLIC_API_ADMIN_TOKEN ?? "").trim();
  if (!admin && typeof window !== "undefined") {
    admin = (window.localStorage.getItem("vg_public_api_admin_token") ?? "").trim();
  }
  if (admin) {
    headers["x-admin-token"] = admin;
  }
  return headers;
}

/**
 * Cree une session appairage ephemere pour QR code mobile.
 *
 * @param payload Parametres token et URL serveur.
 * @returns Code et URI QR (TTL 20 min).
 */
export async function createPairingSession(payload: {
  base_url: string;
  api_token_id?: number;
  create_token_if_missing?: boolean;
  token_name?: string;
}): Promise<MobilePairingSession> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/tokens/pairing-sessions`, {
    method: "POST",
    credentials: "include",
    headers: buildAdminHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Impossible de creer la session appairage (${res.status}).`);
  }
  return (await res.json()) as MobilePairingSession;
}

/**
 * Teste la connexion mobile via /public/mobile/ping (Bearer token).
 *
 * @param bearerToken Token API public mobile.
 * @returns Etat API, WS et modem.
 */
export async function testMobilePing(bearerToken: string): Promise<MobilePingResult> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/public/mobile/ping`, {
    method: "GET",
    headers: { Authorization: `Bearer ${bearerToken}` },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Ping mobile echoue (${res.status}).`);
  }
  return (await res.json()) as MobilePingResult;
}
