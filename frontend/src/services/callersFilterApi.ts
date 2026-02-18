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
  created_at: string;
  updated_at: string;
}

/**
 * Liste des appelants en liste blanche (Permitted, inspire callattendant).
 */
export async function fetchWhitelist(): Promise<Caller[]> {
  const list = await getJson<Caller[]>(`/callers?is_whitelisted=true&limit=500`);
  return Array.isArray(list) ? list : [];
}

/**
 * Liste des appelants en liste noire (Blocked, inspire callattendant).
 */
export async function fetchBlocklist(): Promise<Caller[]> {
  const list = await getJson<Caller[]>(`/callers?is_blocked=true&limit=500`);
  return Array.isArray(list) ? list : [];
}

/**
 * Ajoute un numéro à la liste blanche.
 */
export async function addToWhitelist(
  phone_number: string,
  name?: string | null,
  notes?: string | null
): Promise<Caller> {
  const res = await fetch(`${getApiBaseUrl()}${BASE}/whitelist`, {
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
