/**
 * Appels sortants mobile : REST public + derivation WS audio telephonie.
 */

import { apiGet, apiPost, type ApiConfig } from "./api";
import { log } from "./log";

export interface OutgoingStartResult {
  ok: boolean;
  call_id: number;
  message?: string;
}

export interface MobilePingTelephony {
  ok?: boolean;
  outgoing_ready?: boolean;
  telephony_backend?: string;
  telephony_ws_base?: string | null;
  modem_ok?: boolean;
  transport_ok?: boolean;
}

/**
 * Derive la base WS audio depuis l URL API (port 8000 -> 8090 en LAN).
 *
 * @param apiBaseUrl Base stockee (avec ou sans /api/v1).
 * @returns Ex. ws://node14.lan:8090/ws/outgoing-call
 */
export function deriveTelephonyWsBaseFromApi(apiBaseUrl: string): string {
  const root = apiBaseUrl.replace(/\/api\/v1\/?$/, "").replace(/\/$/, "");
  try {
    const u = new URL(root);
    if (u.port === "8000") {
      u.port = "8090";
    }
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    return `${u.protocol}//${u.host}/ws/outgoing-call`;
  } catch {
    return `${root.replace(/^http/, "ws")}/ws/outgoing-call`;
  }
}

/**
 * Construit l URL WSS PCM complete.
 *
 * @param telephonyBase Base (ex. ws://host:8090/ws/outgoing-call) ou host seul.
 * @param callId ID session.
 */
export function buildOutgoingAudioWsUrl(telephonyBase: string, callId: number): string {
  let base = telephonyBase.replace(/\/$/, "");
  if (!base.includes("/ws/outgoing-call")) {
    base = `${base}/ws/outgoing-call`;
  }
  return `${base}/${callId}/audio`;
}

/**
 * Demarre un appel sortant (API -> daemon -> modem/VoIP).
 *
 * @param cfg Credentials.
 * @param phoneNumber Numero.
 */
export async function startOutgoingCall(
  cfg: ApiConfig,
  phoneNumber: string,
): Promise<OutgoingStartResult> {
  return apiPost<OutgoingStartResult>(cfg, "/public/calls/outgoing/start", {
    phone_number: phoneNumber,
  });
}

/**
 * Raccroche via REST public.
 *
 * @param cfg Credentials.
 * @param callId Session.
 */
export async function hangupOutgoingCall(cfg: ApiConfig, callId: number): Promise<boolean> {
  try {
    await apiPost(cfg, `/public/calls/outgoing/${callId}/hangup`, {});
    return true;
  } catch (err) {
    log.warn("outgoingCall", "hangup failed", err);
    return false;
  }
}

/**
 * DTMF pendant l appel.
 *
 * @param cfg Credentials.
 * @param callId Session.
 * @param digit Touche.
 */
export async function sendOutgoingDtmf(
  cfg: ApiConfig,
  callId: number,
  digit: string,
): Promise<boolean> {
  try {
    await apiPost(cfg, `/public/calls/outgoing/${callId}/dtmf`, { digit });
    return true;
  } catch (err) {
    log.warn("outgoingCall", "dtmf failed", err);
    return false;
  }
}

/**
 * Ping telephonie (backend + WS base).
 *
 * @param cfg Credentials.
 */
export async function pingMobileTelephony(cfg: ApiConfig): Promise<MobilePingTelephony> {
  return apiGet<MobilePingTelephony>(cfg, "/public/mobile/ping");
}
