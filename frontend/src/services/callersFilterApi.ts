/**
 * API liste blanche / liste noire (inspire callattendant Permitted / Blocked).
 */

import { getJson, getApiBaseUrl } from "./httpClient";

const BASE = "/callers";

export interface Caller {
  id: number;
  phone_number: string;
  name: string | null;
  is_blocked: boolean;
  is_whitelisted: boolean;
  notes: string | null;
  greeting_tts_text?: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Liste des appelants en liste blanche (Permitted, inspire callattendant).
 *
 * @param signal AbortSignal optionnel.
 */
export async function fetchWhitelist(signal?: AbortSignal): Promise<Caller[]> {
  const list = await getJson<Caller[]>(
    `/callers?is_whitelisted=true&limit=200`,
    signal
  );
  return Array.isArray(list) ? list : [];
}

/**
 * Liste des appelants en liste noire (Blocked, inspire callattendant).
 *
 * @param signal AbortSignal optionnel.
 */
export async function fetchBlocklist(signal?: AbortSignal): Promise<Caller[]> {
  const list = await getJson<Caller[]>(`/callers?is_blocked=true&limit=200`, signal);
  return Array.isArray(list) ? list : [];
}

/**
 * Ajoute un numéro à la liste blanche.
 */
export async function addToWhitelist(
  phone_number: string,
  name?: string | null,
  notes?: string | null,
  greeting_tts_text?: string | null
): Promise<Caller> {
  const res = await fetch(`${getApiBaseUrl()}${BASE}/whitelist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      phone_number,
      name: name || null,
      notes: notes || null,
      greeting_tts_text: greeting_tts_text || null
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Erreur ${res.status}`);
  }
  return res.json();
}

/**
 * Ajoute un numéro à la liste noire.
 */
export async function addToBlocklist(
  phone_number: string,
  name?: string | null,
  notes?: string | null
): Promise<Caller> {
  const res = await fetch(`${getApiBaseUrl()}${BASE}/block`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone_number, name: name || null, notes: notes || null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Erreur ${res.status}`);
  }
  return res.json();
}

/**
 * Retire un appelant de la liste blanche (met is_whitelisted à false).
 */
export async function removeFromWhitelist(callerId: number): Promise<Caller> {
  const res = await fetch(`${getApiBaseUrl()}${BASE}/${callerId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_whitelisted: false }),
  });
  if (!res.ok) throw new Error(`Erreur ${res.status}`);
  return res.json();
}

/**
 * Retire un appelant de la liste noire (met is_blocked à false).
 */
export async function removeFromBlocklist(callerId: number): Promise<Caller> {
  const res = await fetch(`${getApiBaseUrl()}${BASE}/${callerId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_blocked: false }),
  });
  if (!res.ok) throw new Error(`Erreur ${res.status}`);
  return res.json();
}

/**
 * Cree un appelant (sans forcer liste blanche / noire).
 */
export async function createCallerRecord(payload: {
  phone_number: string;
  name?: string | null;
  is_whitelisted?: boolean;
  is_blocked?: boolean;
  greeting_tts_text?: string | null;
}): Promise<Caller> {
  const res = await fetch(`${getApiBaseUrl()}${BASE}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      phone_number: payload.phone_number,
      name: payload.name ?? null,
      is_whitelisted: payload.is_whitelisted ?? false,
      is_blocked: payload.is_blocked ?? false,
      greeting_tts_text: payload.greeting_tts_text ?? null
    })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Erreur ${res.status}`);
  }
  return res.json();
}

/**
 * Met a jour un appelant (filtrage, accueil perso).
 *
 * @param callerId Identifiant appelant.
 * @param patch Champs a modifier.
 */
export async function updateCaller(
  callerId: number,
  patch: {
    name?: string | null;
    notes?: string | null;
    is_whitelisted?: boolean;
    is_blocked?: boolean;
    greeting_tts_text?: string | null;
  }
): Promise<Caller> {
  const res = await fetch(`${getApiBaseUrl()}${BASE}/${callerId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Erreur ${res.status}`);
  }
  return res.json();
}

/**
 * Charge l'appelant associe a un numero (filtrage / accueil).
 *
 * @param phone Numero tel.
 * @param signal AbortSignal optionnel.
 */
export async function fetchCallerByPhone(phone: string, signal?: AbortSignal): Promise<Caller | null> {
  const q = new URLSearchParams({ phone_number: phone.trim() });
  const list = await getJson<Caller[]>(`/callers?${q.toString()}`, signal);
  return Array.isArray(list) && list.length > 0 ? list[0] : null;
}
