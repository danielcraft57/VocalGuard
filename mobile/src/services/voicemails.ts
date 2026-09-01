/**
 * API messages vocaux (Bearer public mobile).
 */
import { apiGet, ApiConfig, buildApiUrl } from "./api";

/**
 * URL stream audio WAV authentifie.
 *
 * @param config API mobile.
 * @param id Identifiant message.
 */
export function voicemailAudioUrl(config: ApiConfig, id: number): string {
  return buildApiUrl(config.baseUrl, `/public/voicemails/${id}/audio`);
}

/**
 * Marque un message vocal comme lu.
 *
 * @param config API mobile.
 * @param id Identifiant message.
 */
export async function markVoicemailRead(config: ApiConfig, id: number): Promise<void> {
  const url = buildApiUrl(config.baseUrl, `/public/voicemails/${id}/read`);
  const res = await fetch(url, {
    method: "PUT",
    headers: { Authorization: `Bearer ${config.token}` },
  });
  if (!res.ok) {
    throw new Error(`Marquer lu echoue: ${res.status}`);
  }
}

/**
 * Ping stats messages (non lus) via delta leger.
 *
 * @param config API mobile.
 */
export async function fetchUnreadVoicemailCount(config: ApiConfig): Promise<number> {
  const data = await apiGet<{ total: number; voicemails: unknown[] }>(
    config,
    "/public/voicemails?limit=1&is_read=false",
  );
  return Number(data.total ?? 0);
}
