import { getApiBaseUrl } from "./httpClient";

export type IncomingLineMode = "voicemail" | "phone";

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
