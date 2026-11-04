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
  profile?: string;
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
  profile?: "inbound" | "outbound_commercial";
};

export type KbIntentPatch = {
  responses?: string[];
  patterns?: string[];
  enabled?: boolean;
  priority?: number;
  action?: string | null;
  clear_action?: boolean;
};

/** Options regen voix intents (overrides TTS). */
export type KbVoiceRegenOptions = {
  force?: boolean;
  tags?: string[];
  profile?: "inbound" | "outbound_commercial";
  tts_provider?: "edge" | "elevenlabs";
  edge_tts_voice?: string;
  edge_tts_rate?: string;
  edge_tts_pitch?: string;
  tts_voice_gain_db?: number;
  elevenlabs_voice_id?: string;
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
 * @param profile inbound | outbound_commercial (undefined = tous).
 * @returns Intents.
 */
export async function fetchKbIntents(
  enabledOnly = false,
  signal?: AbortSignal,
  profile?: "inbound" | "outbound_commercial"
): Promise<KbIntent[]> {
  const params = new URLSearchParams();
  if (enabledOnly) params.set("enabled_only", "true");
  if (profile) params.set("profile", profile);
  const q = params.toString() ? `?${params.toString()}` : "";
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
  recentUserTexts: string[] = [],
  profile: "inbound" | "outbound_commercial" = "inbound"
): Promise<KbChatReply> {
  const res = await fetch(`${getApiBaseUrl()}/kb/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      top_k: 8,
      profile,
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
 * Supprime tous les intents d'un profil.
 *
 * @param profile inbound | outbound_commercial.
 * @returns Nombre supprime.
 */
export async function wipeKbProfileIntents(
  profile: "inbound" | "outbound_commercial"
): Promise<number> {
  const res = await fetch(
    `${getApiBaseUrl()}/kb/profiles/${encodeURIComponent(profile)}/intents`,
    { method: "DELETE" }
  );
  if (!res.ok) {
    throw new Error(`KB wipe HTTP ${res.status}`);
  }
  const body = (await res.json()) as { deleted?: number };
  return Number(body.deleted || 0);
}

/**
 * Regenerere les voix intents (params TTS override optionnels).
 *
 * @param options Force / profile / voix.
 */
export async function regenerateKbVoices(
  options: boolean | KbVoiceRegenOptions = false
): Promise<{
  ok: number;
  skipped: number;
  failed: number;
}> {
  const opts: KbVoiceRegenOptions =
    typeof options === "boolean" ? { force: options } : options || {};
  const body: Record<string, unknown> = {
    force: opts.force ?? false
  };
  if (opts.tags?.length) body.tags = opts.tags;
  if (opts.profile) body.profile = opts.profile;
  if (opts.tts_provider) body.tts_provider = opts.tts_provider;
  if (opts.edge_tts_voice) body.edge_tts_voice = opts.edge_tts_voice;
  if (opts.edge_tts_rate) body.edge_tts_rate = opts.edge_tts_rate;
  if (opts.edge_tts_pitch) body.edge_tts_pitch = opts.edge_tts_pitch;
  if (opts.tts_voice_gain_db !== undefined) {
    body.tts_voice_gain_db = opts.tts_voice_gain_db;
  }
  if (opts.elevenlabs_voice_id) body.elevenlabs_voice_id = opts.elevenlabs_voice_id;

  const res = await fetch(`${getApiBaseUrl()}/kb/voices/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!res.ok) {
    throw new Error(`KB voices HTTP ${res.status}`);
  }
  return (await res.json()) as { ok: number; skipped: number; failed: number };
}

/** Options apercu TTS une phrase. */
export type KbVoicePreviewOptions = {
  text: string;
  tts_provider?: "edge" | "elevenlabs";
  edge_tts_voice?: string;
  edge_tts_rate?: string;
  edge_tts_pitch?: string;
  tts_voice_gain_db?: number;
  elevenlabs_voice_id?: string;
  /** Ecrit le WAV modem de cette variante seulement. */
  save_tag?: string;
  save_index?: number;
  profile?: "inbound" | "outbound_commercial";
};

/**
 * Apercu TTS d'une phrase (blob audio navigateur).
 *
 * @param options Texte + prefs voix.
 * @returns Blob audio + flag saved.
 */
export async function previewKbVoice(
  options: KbVoicePreviewOptions
): Promise<{ blob: Blob; saved: boolean }> {
  const res = await fetch(`${getApiBaseUrl()}/kb/voices/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options)
  });
  if (!res.ok) {
    let detail = `KB preview HTTP ${res.status}`;
    try {
      const err = (await res.json()) as { detail?: string };
      if (err.detail) detail = String(err.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const saved = res.headers.get("X-VG-Saved") === "1";
  return { blob, saved };
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
