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
 * True si l'erreur vient d'un abort (navigation / unmount).
 *
 * @param err Erreur catch.
 */
export function isAbortError(err: unknown): boolean {
  if (!err) return false;
  if (typeof DOMException !== "undefined" && err instanceof DOMException) {
    return err.name === "AbortError";
  }
  return (
    typeof err === "object" &&
    err !== null &&
    "name" in err &&
    (err as { name?: string }).name === "AbortError"
  );
}

/**
 * Liste les intents KB.
 *
 * @param enabledOnly Filtre enabled.
 * @param signal AbortSignal (annule au changement de page).
 * @returns Intents.
 */
export async function fetchKbIntents(
  enabledOnly = false,
  signal?: AbortSignal
): Promise<KbIntent[]> {
  const q = enabledOnly ? "?enabled_only=true" : "";
  const res = await fetch(`${getApiBaseUrl()}/kb/intents${q}`, { signal });
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

export type KbConversationStatus = {
  ready: boolean;
  stt_configured: boolean;
  stt_ok: boolean;
  stt_detail?: string | null;
  intents_enabled: number;
  voices_ready: number;
  voices_complete: boolean;
  qdrant_configured?: boolean;
  qdrant_ok?: boolean;
  qdrant_url?: string | null;
  qdrant_points?: number;
  qdrant_collection?: string | null;
  qdrant_detail?: string | null;
  qdrant_points_outbound?: number;
  qdrant_ok_outbound?: boolean;
  qdrant_collection_outbound?: string | null;
  vector_engine?: string | null;
};

/**
 * Statut de readiness du mode conversation (STT + intents + voix).
 *
 * @param signal AbortSignal optionnel.
 * @returns Snapshot pret / compteurs.
 */
export async function fetchKbConversationStatus(
  signal?: AbortSignal
): Promise<KbConversationStatus> {
  const res = await fetch(`${getApiBaseUrl()}/kb/conversation-status`, { signal });
  if (!res.ok) {
    throw new Error(`KB conversation-status HTTP ${res.status}`);
  }
  return (await res.json()) as KbConversationStatus;
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

import type { ChatMsg } from "../components/kb/chatHistory";

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
 * @param signal AbortSignal optionnel.
 */
export async function fetchKbChats(
  limit = 30,
  signal?: AbortSignal
): Promise<KbChatSessionDto[]> {
  const res = await fetch(`${getApiBaseUrl()}/kb/chats?limit=${limit}`, { signal });
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
 * @param signal AbortSignal optionnel.
 */
export async function importKbChats(
  sessions: KbChatSessionDto[],
  signal?: AbortSignal
): Promise<number> {
  const res = await fetch(`${getApiBaseUrl()}/kb/chats/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessions }),
    signal
  });
  if (!res.ok) {
    throw new Error(`KB chat import HTTP ${res.status}`);
  }
  const body = (await res.json()) as { imported?: number };
  return Number(body.imported || 0);
}
