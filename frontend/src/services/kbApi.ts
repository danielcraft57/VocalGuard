/**
 * Client API Base de connaissances (intents).
 */

import { getApiBaseUrl } from "./httpClient";

export type KbIntent = {
  id: number;
  tag: string;
  source?: string;
  niveau?: number;
  enabled: boolean;
  priority: number;
  wav_basename?: string | null;
  action?: string | null;
  patterns: string[];
  responses: string[];
  has_wav?: boolean;
};

export type KbPredictItem = {
  tag: string;
  score: number;
};

export type KbChatReply = {
  reply: string;
  tag: string | null;
  score: number;
  action?: string | null;
  response_index?: number;
  top_predictions: KbPredictItem[];
  raw_predictions?: KbPredictItem[];
  source?: string;
  persona_reason?: string | null;
  mood?: {
    patience: number;
    tone: string;
    user_repeat: number;
    tag_streak: number;
  } | null;
};

export type KbIntentCreate = {
  tag: string;
  patterns: string[];
  responses: string[];
  priority?: number;
  enabled?: boolean;
  action?: string | null;
  niveau?: number;
};

export type KbIntentPatch = {
  responses?: string[];
  patterns?: string[];
  enabled?: boolean;
  priority?: number;
  action?: string | null;
  clear_action?: boolean;
};

/**
 * Liste les intents KB.
 *
 * @param enabledOnly Filtre enabled.
 * @returns Intents.
 */
export async function fetchKbIntents(enabledOnly = false): Promise<KbIntent[]> {
  const q = enabledOnly ? "?enabled_only=true" : "";
  const res = await fetch(`${getApiBaseUrl()}/kb/intents${q}`);
  if (!res.ok) {
    throw new Error(`KB intents HTTP ${res.status}`);
  }
  const body = (await res.json()) as { intents?: KbIntent[] };
  return Array.isArray(body.intents) ? body.intents : [];
}

/**
 * Predict intents pour un texte.
 *
 * @param text Phrase.
 * @returns Predictions.
 */
export async function predictKbIntent(text: string): Promise<KbPredictItem[]> {
  const res = await fetch(`${getApiBaseUrl()}/kb/intent-predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, top_k: 8 })
  });
  if (!res.ok) {
    throw new Error(`KB predict HTTP ${res.status}`);
  }
  const body = (await res.json()) as { top_predictions?: KbPredictItem[] };
  return Array.isArray(body.top_predictions) ? body.top_predictions : [];
}

/**
 * Tour de tchat KB (predict + persona dialogue).
 *
 * @param text Message utilisateur.
 * @param recentReplies Reponses bot deja dites.
 * @param recentTags Tags deja choisis.
 * @param recentUserTexts Messages user deja envoyes.
 * @returns Reponse bot + scores + mood.
 */
export async function chatKb(
  text: string,
  recentReplies: string[] = [],
  recentTags: string[] = [],
  recentUserTexts: string[] = []
): Promise<KbChatReply> {
  const res = await fetch(`${getApiBaseUrl()}/kb/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      top_k: 8,
      recent_replies: recentReplies.slice(-12),
      recent_tags: recentTags.slice(-12),
      recent_user_texts: recentUserTexts.slice(-12)
    })
  });
  if (!res.ok) {
    throw new Error(`KB chat HTTP ${res.status}`);
  }
  return (await res.json()) as KbChatReply;
}

/**
 * Cree un intent.
 *
 * @param payload Tag + patterns + responses.
 */
export async function createKbIntent(payload: KbIntentCreate): Promise<KbIntent> {
  const res = await fetch(`${getApiBaseUrl()}/kb/intents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    let detail = `KB create HTTP ${res.status}`;
    try {
      const err = (await res.json()) as { detail?: string };
      if (err.detail) detail = String(err.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await res.json()) as KbIntent;
}

/**
 * Met a jour un intent.
 *
 * @param tag Tag.
 * @param patch Champs.
 */
export async function patchKbIntent(tag: string, patch: KbIntentPatch): Promise<KbIntent> {
  const res = await fetch(`${getApiBaseUrl()}/kb/intents/${encodeURIComponent(tag)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch)
  });
  if (!res.ok) {
    throw new Error(`KB patch HTTP ${res.status}`);
  }
  return (await res.json()) as KbIntent;
}

/**
 * Supprime un intent.
 *
 * @param tag Tag.
 */
export async function deleteKbIntent(tag: string): Promise<void> {
  const res = await fetch(`${getApiBaseUrl()}/kb/intents/${encodeURIComponent(tag)}`, {
    method: "DELETE"
  });
  if (!res.ok) {
    throw new Error(`KB delete HTTP ${res.status}`);
  }
}

/**
 * Regenerere les voix intents (params accueil).
 *
 * @param force Ignore cache.
 */
export async function regenerateKbVoices(force = false): Promise<{
  ok: number;
  skipped: number;
  failed: number;
}> {
  const res = await fetch(`${getApiBaseUrl()}/kb/voices/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force })
  });
  if (!res.ok) {
    throw new Error(`KB voices HTTP ${res.status}`);
  }
  return (await res.json()) as { ok: number; skipped: number; failed: number };
}

/**
 * URL d'ecoute du WAV modem d'un intent.
 *
 * @param tag Tag intent.
 * @returns URL GET.
 */
export function getKbIntentVoiceUrl(tag: string): string {
  return `${getApiBaseUrl()}/kb/intents/${encodeURIComponent(tag)}/voice`;
}

import type { ChatMsg } from "../app/kb/chatHistory";

export type KbChatSessionDto = {
  id: string;
  title: string;
  messages: ChatMsg[];
  recentReplies: string[];
  recentTags: string[];
  recentUserTexts: string[];
  createdAt?: string | null;
  updatedAt?: string | null;
};

/**
 * Liste les sessions tchatche (BDD).
 *
 * @param limit Cap.
 */
export async function fetchKbChats(limit = 30): Promise<KbChatSessionDto[]> {
  const res = await fetch(`${getApiBaseUrl()}/kb/chats?limit=${limit}`);
  if (!res.ok) {
    throw new Error(`KB chats HTTP ${res.status}`);
  }
  const body = (await res.json()) as { sessions?: KbChatSessionDto[] };
  return Array.isArray(body.sessions) ? body.sessions : [];
}

/**
 * Sauve / met a jour une session tchatche.
 *
 * @param session Payload.
 */
export async function upsertKbChat(session: KbChatSessionDto): Promise<KbChatSessionDto> {
  const res = await fetch(`${getApiBaseUrl()}/kb/chats/${encodeURIComponent(session.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(session)
  });
  if (!res.ok) {
    throw new Error(`KB chat save HTTP ${res.status}`);
  }
  return (await res.json()) as KbChatSessionDto;
}

/**
 * Supprime une session tchatche.
 *
 * @param id Id session.
 */
export async function deleteKbChat(id: string): Promise<void> {
  const res = await fetch(`${getApiBaseUrl()}/kb/chats/${encodeURIComponent(id)}`, {
    method: "DELETE"
  });
  if (!res.ok) {
    throw new Error(`KB chat delete HTTP ${res.status}`);
  }
}

/**
 * Importe un lot (migration localStorage → BDD).
 *
 * @param sessions Sessions locales.
 */
export async function importKbChats(sessions: KbChatSessionDto[]): Promise<number> {
  const res = await fetch(`${getApiBaseUrl()}/kb/chats/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessions })
  });
  if (!res.ok) {
    throw new Error(`KB chat import HTTP ${res.status}`);
  }
  const body = (await res.json()) as { imported?: number };
  return Number(body.imported || 0);
}
