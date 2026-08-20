/**
 * API messages vocaux (apres le bip).
 */

import { getApiBaseUrl } from "./httpClient";

export interface Voicemail {
  id: number;
  call_id?: number | null;
  caller_id?: number | null;
  phone_number?: string | null;
  caller_name?: string | null;
  audio_file: string;
  transcription?: string | null;
  duration?: number | null;
  is_read: boolean;
  is_archived: boolean;
  created_at: string;
}

/**
 * Liste les messages vocaux recents.
 *
 * @param opts Filtres optionnels.
 * @returns Messages tries du plus recent au plus ancien.
 */
export async function fetchVoicemails(opts?: {
  skip?: number;
  limit?: number;
  is_read?: boolean;
}): Promise<Voicemail[]> {
  const base = getApiBaseUrl();
  const params = new URLSearchParams();
  if (opts?.skip != null) params.set("skip", String(opts.skip));
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.is_read != null) params.set("is_read", String(opts.is_read));
  const qs = params.toString();
  const res = await fetch(`${base}/voicemails${qs ? `?${qs}` : ""}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Erreur API messages: ${res.status}`);
  }
  return (await res.json()) as Voicemail[];
}

/**
 * URL de lecture audio d un message.
 *
 * @param id Identifiant du message.
 * @returns URL absolute same-origin.
 */
export function voicemailAudioUrl(id: number): string {
  return `${getApiBaseUrl()}/voicemails/${id}/audio`;
}

/**
 * Marque un message comme lu.
 *
 * @param id Identifiant du message.
 */
export async function markVoicemailRead(id: number): Promise<void> {
  const res = await fetch(`${getApiBaseUrl()}/voicemails/${id}/read`, { method: "PUT" });
  if (!res.ok) {
    throw new Error(`Impossible de marquer lu: ${res.status}`);
  }
}

/**
 * Supprime un message vocal.
 *
 * @param id Identifiant du message.
 */
export async function deleteVoicemail(id: number): Promise<void> {
  const res = await fetch(`${getApiBaseUrl()}/voicemails/${id}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(`Suppression impossible: ${res.status}`);
  }
}
