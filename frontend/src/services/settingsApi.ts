import { getApiBaseUrl } from "./httpClient";

export type IncomingLineMode = "voicemail" | "phone";

export type IncomingCallConfig = {
  incoming_line_mode: IncomingLineMode;
  cid_wait_sec: number;
  instant_seize_cid_grace_sec: number;
  ring_cycle_sec: number;
  ring_quiet_abort_sec: number;
  max_incoming_wait_sec: number;
  phone_mode_rings: number;
  whitelist_ring_only: boolean;
  whitelist_match: "exact" | "prefix" | "e164_normalize";
  screened_when_unknown: boolean;
  active_preset: IncomingLineMode;
  presets: Record<string, unknown>;
  profiles: Record<string, unknown>;
  profile_overrides: Record<string, unknown>;
  audio: Record<string, unknown>;
  voicemail: Record<string, unknown>;
  number_patterns: Record<string, unknown>;
  advanced: Record<string, unknown>;
  rings_before_answer: number;
  incoming_auto_answer: boolean;
};

export type IncomingCallConfigPatch = Partial<
  Pick<
    IncomingCallConfig,
    | "cid_wait_sec"
    | "instant_seize_cid_grace_sec"
    | "ring_cycle_sec"
    | "ring_quiet_abort_sec"
    | "max_incoming_wait_sec"
    | "phone_mode_rings"
    | "whitelist_ring_only"
    | "whitelist_match"
    | "screened_when_unknown"
    | "presets"
    | "profiles"
    | "profile_overrides"
    | "audio"
    | "voicemail"
    | "number_patterns"
    | "advanced"
  >
>;

export type SettingsSnapshot = {
  database_url: string;
  api_host: string;
  api_port: number;
  modem_port?: string | null;
  voice_language: string;
  rings_before_answer: number;
  voicemail_enabled: boolean;
  incoming_auto_answer: boolean;
  incoming_line_mode: IncomingLineMode;
};

export type TelephonyStatus = {
  status: string;
  modem_initialized: boolean;
  modem_port?: string | null;
  firmware_ati3?: string | null;
  last_ring_at?: number | null;
  last_cid_raw?: string | null;
  last_error?: string | null;
  incoming_line_mode: IncomingLineMode;
  in_call: boolean;
  relay_failures: number;
  daemon_reachable?: boolean | null;
};

/**
 * Lit le snapshot settings (mode ligne entrante inclus).
 *
 * @returns Configuration metier.
 */
export async function fetchSettings(): Promise<SettingsSnapshot> {
  const res = await fetch(`${getApiBaseUrl()}/settings`);
  if (!res.ok) {
    throw new Error(`Erreur API settings: ${res.status}`);
  }
  return (await res.json()) as SettingsSnapshot;
}

/**
 * Lit la configuration complete des appels entrants.
 */
export async function fetchIncomingCallConfig(): Promise<IncomingCallConfig> {
  const res = await fetch(`${getApiBaseUrl()}/settings/incoming-call`);
  if (!res.ok) {
    throw new Error(`Erreur API incoming-call: ${res.status}`);
  }
  return (await res.json()) as IncomingCallConfig;
}

/**
 * Met a jour partiellement la configuration appels entrants.
 */
export async function patchIncomingCallConfig(
  patch: IncomingCallConfigPatch
): Promise<IncomingCallConfig> {
  const res = await fetch(`${getApiBaseUrl()}/settings/incoming-call`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch)
  });
  if (!res.ok) {
    let detail = `Erreur API incoming-call: ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await res.json()) as IncomingCallConfig;
}

/**
 * Etat modem / daemon (pastille topbar).
 *
 * @returns Snapshot telephonie.
 */
export async function fetchTelephonyStatus(): Promise<TelephonyStatus> {
  const res = await fetch(`${getApiBaseUrl()}/telephony/status`);
  if (!res.ok) {
    throw new Error(`Erreur API telephony status: ${res.status}`);
  }
  return (await res.json()) as TelephonyStatus;
}

/**
 * Bascule répondeur (coupe-sonnerie) / téléphone parallèle.
 *
 * @param mode Mode cible.
 * @returns Settings a jour.
 */
export async function setIncomingLineMode(mode: IncomingLineMode): Promise<SettingsSnapshot> {
  const res = await fetch(`${getApiBaseUrl()}/settings/incoming-line-mode`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode })
  });
  if (!res.ok) {
    let detail = `Erreur API mode ligne: ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await res.json()) as SettingsSnapshot;
}
