/**
 * API regles de blocage (pattern exact, prefixe, regex).
 * Inspire callattendant BLOCK_NUMBER_PATTERNS / BLOCK_NAME_PATTERNS.
 */

import { getJson, getApiBaseUrl } from "./httpClient";

const BASE = "/block-rules";

export interface BlockRule {
  id: number;
  name: string;
  pattern: string;
  pattern_type: "exact" | "prefix" | "regex";
  is_active: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export async function fetchBlockRules(): Promise<BlockRule[]> {
  const list = await getJson<BlockRule[]>(BASE);
  return Array.isArray(list) ? list : [];
}

export async function createBlockRule(
  name: string,
  pattern: string,
  pattern_type: "exact" | "prefix" | "regex",
  description?: string | null
): Promise<BlockRule> {
  const res = await fetch(`${getApiBaseUrl()}${BASE}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, pattern, pattern_type, description: description || null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Erreur ${res.status}`);
  }
  return res.json();
}

export async function deleteBlockRule(ruleId: number): Promise<void> {
  const res = await fetch(`${getApiBaseUrl()}${BASE}/${ruleId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Erreur ${res.status}`);
}
