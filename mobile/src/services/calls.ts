/**
 * API appels (Bearer public mobile) : detail + enregistrement.
 */
import { apiGet, ApiConfig, buildApiUrl, ApiHttpError } from "./api";
import { downloadAuthAudio } from "./downloadAudio";

/** Detail appel renvoye par GET /public/calls/{id}. */
export interface CallDetail {
  id: number;
  phone_number?: string | null;
  caller_name?: string | null;
  call_time?: string | null;
  status?: string | null;
  duration?: number | null;
  transcription?: string | null;
  audio_file?: string | null;
  no_message?: boolean;
  extra_data?: Record<string, unknown> | null;
  osint?: Record<string, unknown> | null;
}

/**
 * Charge le detail d un appel (OSINT + cues).
 *
 * @param config API mobile.
 * @param callId Identifiant.
 * @returns Detail.
 */
export async function fetchCallDetail(config: ApiConfig, callId: number): Promise<CallDetail> {
  return apiGet<CallDetail>(config, `/public/calls/${callId}`);
}

/**
 * Charge le detail sans faire echouer l UI (404 = API pas encore deployee).
 *
 * @param config API mobile.
 * @param callId Identifiant.
 * @returns Detail ou null + message d erreur.
 */
export async function fetchCallDetailSoft(
  config: ApiConfig,
  callId: number,
): Promise<{ detail: CallDetail | null; error: string | null }> {
  try {
    const detail = await fetchCallDetail(config, callId);
    return { detail, error: null };
  } catch (err) {
    const status = err instanceof ApiHttpError ? err.status : 0;
    const msg =
      status === 404
        ? "Detail API indisponible (deploie le backend ou utilise le cache local)."
        : status === 401
          ? "Token refuse (401)."
          : err instanceof Error
            ? err.message
            : "Detail indisponible.";
    return { detail: null, error: msg };
  }
}

/**
 * URL stream audio WAV authentifie.
 *
 * @param config API mobile.
 * @param callId Identifiant appel.
 */
export function callRecordingUrl(config: ApiConfig, callId: number): string {
  return buildApiUrl(config.baseUrl, `/public/calls/${callId}/recording`);
}

/**
 * Telecharge le WAV d un appel (file:// natif, blob: web).
 *
 * @param config API mobile.
 * @param callId Identifiant.
 * @returns URI jouable.
 */
export async function downloadCallRecording(config: ApiConfig, callId: number): Promise<string> {
  return downloadAuthAudio(config, callRecordingUrl(config, callId), `call_${callId}.wav`);
}
