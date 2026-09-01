import { getApiBaseUrl, getJson } from "./httpClient";

export interface Call {
  id: number;
  caller_id?: number | null;
  phone_number?: string | null;
  caller_name?: string | null;
  call_time: string;
  answer_time?: string | null;
  end_time?: string | null;
  status: string;
  duration?: number | null;
  transcription?: string | null;
  audio_file?: string | null;
  extra_data?: Record<string, unknown> | null;
}

export interface CallListResponse {
  total: number;
  skip: number;
  limit: number;
  calls: Call[];
}

export interface OsintReputation {
  phone_number: string;
  reputation: string;
  is_spam: boolean;
  is_scam: boolean;
  is_commercial: boolean;
  is_telemarketer: boolean;
  confidence: number;
  sources: string[];
  recommendation: string;
  city?: string | null;
  region?: string | null;
  operator?: string | null;
}

export interface CallWithOsint extends Call {
  osint?: OsintReputation | null;
}

/**
 * Recupere la liste des appels avec la reputation OSINT depuis la base (un seul appel API, rapide).
 * Les numeros deja enrichis en base (migration --run-osint ou appels recents) auront leur reputation.
 */
export async function fetchCallsWithOsint(): Promise<CallWithOsint[]> {
  const data = await getJson<CallListResponse & { calls: CallWithOsint[] }>(
    "/calls?with_osint=true&limit=500"
  );
  return data.calls ?? [];
}

export async function fetchCallWithOsintById(callId: number): Promise<CallWithOsint> {
  return getJson<CallWithOsint>(`/calls/${callId}?with_osint=true`);
}

export function getCallRecordingUrl(callId: number): string {
  return `${getApiBaseUrl()}/calls/${callId}/recording`;
}

export async function deleteCall(callId: number): Promise<void> {
  const res = await fetch(`${getApiBaseUrl()}/calls/${callId}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(`Suppression appel ${callId}: ${res.status}`);
  }
}

export async function bulkDeleteCalls(ids: number[]): Promise<{ deleted: number }> {
  return postJson<{ deleted: number }>("/calls/bulk-delete", { ids });
}

export interface OutgoingCallActionResponse {
  ok: boolean;
  call_id: number;
  message: string;
}

const TELEPHONY_DEV_HINT_FR =
  "Backend avec modem sur un Raspberry Pi : le daemon doit tourner (port 8090) et TELEPHONY_DAEMON_URL doit être joignable depuis ce PC (ex. http://192.168.1.xx:8090). Sur ce PC sans modem ni daemon local : mettez USE_TELEPHONY_DAEMON=0 dans le .env du backend puis redémarrez uvicorn.";

function outgoingTelephonyHintNeeded(status: number, detail: string, path: string): boolean {
  if (!path.startsWith("/calls/outgoing")) return false;
  if (status !== 502 && status !== 503) return false;
  return !/USE_TELEPHONY_DAEMON|TELEPHONY_DAEMON_URL|service telephony|daemon|8090|injoignable/i.test(detail);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const rawText = await res.text();
  if (!res.ok) {
    let detail = `Erreur API POST ${path}: ${res.status}`;
    try {
      const j = JSON.parse(rawText) as { detail?: unknown };
      if (j?.detail != null) {
        detail =
          typeof j.detail === "string"
            ? j.detail
            : Array.isArray(j.detail)
              ? j.detail.map((x: unknown) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: string }).msg) : String(x))).join("; ")
              : JSON.stringify(j.detail);
      }
    } catch {
      const snippet = rawText.trim().slice(0, 400);
      if (snippet) {
        detail = `${detail} — ${snippet}`;
      }
    }
    const telephonyHintAlready =
      /USE_TELEPHONY_DAEMON|TELEPHONY_DAEMON_URL|service telephony|daemon.*8090/i.test(detail);
    if (
      !telephonyHintAlready &&
      (res.status === 405 ||
        (/\bmethod not allowed\b/i.test(detail) && path.startsWith("/calls/outgoing")))
    ) {
      detail = `${detail} — Vérifiez NEXT_PUBLIC_API_BASE_URL (ex. http://localhost:8000/api/v1). Sans modem local : USE_TELEPHONY_DAEMON=0 dans .env backend. Avec Pi : TELEPHONY_DAEMON_URL doit pointer vers le daemon téléphonie (ex. :8090), pas la page web.`;
    }
    if (outgoingTelephonyHintNeeded(res.status, detail, path)) {
      detail = `${detail}\n\n${TELEPHONY_DEV_HINT_FR}`;
    }
    throw new Error(detail);
  }
  try {
    return JSON.parse(rawText) as T;
  } catch {
    throw new Error(`Réponse JSON invalide pour POST ${path}`);
  }
}

export async function startOutgoingCall(phoneNumber: string): Promise<OutgoingCallActionResponse> {
  return postJson<OutgoingCallActionResponse>("/calls/outgoing/start", { phone_number: phoneNumber });
}

export async function sendOutgoingDtmf(callId: number, digit: string): Promise<OutgoingCallActionResponse> {
  return postJson<OutgoingCallActionResponse>(`/calls/outgoing/${callId}/dtmf`, { digit });
}

export async function hangupOutgoingCall(callId: number): Promise<OutgoingCallActionResponse> {
  return postJson<OutgoingCallActionResponse>(`/calls/outgoing/${callId}/hangup`, {});
}

/**
 * Raccroche un appel entrant en cours (repondeur).
 */
export async function hangupIncomingCall(callId: number): Promise<OutgoingCallActionResponse> {
  return postJson<OutgoingCallActionResponse>(`/calls/incoming/${callId}/hangup`, {});
}

export type CallUiTag = "permitted" | "restricted" | "unknown" | "blocked" | "commercial" | "none";

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!res.ok) {
    throw new Error(`Erreur API PATCH ${path}: ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function patchCallTag(callId: number, tag: CallUiTag): Promise<{ ok: boolean }> {
  return patchJson<{ ok: boolean }>(`/calls/${callId}/tag`, { tag });
}

export async function queueCallOsint(callId: number): Promise<{ ok: boolean }> {
  const res = await fetch(`${getApiBaseUrl()}/calls/${callId}/osint/queue`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Erreur API POST osint/queue: ${res.status}`);
  }
  return (await res.json()) as { ok: boolean };
}

