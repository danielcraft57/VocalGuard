/**
 * API co-pilote appel commercial sortant (top-5 intents + 5 phrases).
 */

import { getApiBaseUrl } from "./httpClient";

export type CommercialSuggestion = {
  rank: number;
  key: string;
  tag: string;
  score: number;
  preview: string;
  action?: string | null;
  niveau?: number;
  phrases_count?: number;
  wav_ready_any?: boolean;
};

export type CommercialPhrase = {
  rank: number;
  key: string;
  text: string;
  variant_index: number;
  wav_basename: string;
  wav_ready: boolean;
};

export type CommercialSuggestResult = {
  text: string;
  engine: string;
  profile: string;
  suggestions: CommercialSuggestion[];
};

export type CommercialPhrasesResult = {
  tag: string;
  action?: string | null;
  phrases: CommercialPhrase[];
};

export type CommercialChooseResult = {
  ok: boolean;
  played: boolean;
  play_error?: string | null;
  tag: string;
  variant_index: number;
  text: string;
  wav_basename: string;
  action?: string | null;
};

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!res.ok) {
    const raw = await res.text().catch(() => "");
    throw new Error(raw || `HTTP ${res.status} ${path}`);
  }
  return (await res.json()) as T;
}

/**
 * Predict top-5 situations commerciales.
 *
 * @param text Texte STT / saisie.
 * @param callId Session sortante optionnelle.
 */
export async function suggestCommercial(
  text: string,
  callId?: number | null
): Promise<CommercialSuggestResult> {
  return postJson<CommercialSuggestResult>("/kb/outbound-commercial/suggest", {
    text,
    top_k: 5,
    call_id: callId ?? undefined
  });
}

/**
 * Charge les 5 formulations d'un intent.
 *
 * @param tag Tag intent.
 */
export async function fetchCommercialPhrases(tag: string): Promise<CommercialPhrasesResult> {
  return postJson<CommercialPhrasesResult>("/kb/outbound-commercial/phrases", { tag });
}

/**
 * Choisit une phrase et joue le WAV sur la ligne.
 *
 * @param tag Tag intent.
 * @param variantIndex Index 0..4.
 * @param callId Session sortante.
 * @param play Jouer sur le modem.
 */
export async function chooseCommercialPhrase(
  tag: string,
  variantIndex: number,
  callId?: number | null,
  play = true
): Promise<CommercialChooseResult> {
  return postJson<CommercialChooseResult>("/kb/outbound-commercial/choose", {
    tag,
    variant_index: variantIndex,
    call_id: callId ?? undefined,
    play
  });
}

/**
 * Formulations d'ouverture (presentation).
 */
export async function fetchCommercialPresentation(): Promise<CommercialPhrasesResult> {
  const res = await fetch(`${getApiBaseUrl()}/kb/outbound-commercial/presentation`);
  if (!res.ok) {
    throw new Error(`presentation HTTP ${res.status}`);
  }
  return (await res.json()) as CommercialPhrasesResult;
}

/**
 * URL de lecture d'un WAV commercial (HP navigateur).
 *
 * @param basename Sans extension.
 */
export function getCommercialVoiceUrl(basename: string): string {
  return `${getApiBaseUrl()}/kb/outbound-commercial/voice/${encodeURIComponent(basename)}`;
}

/**
 * Prefetch voix sortantes (Edge ou ElevenLabs).
 *
 * @param force Ignore cache.
 * @param ttsProvider edge | elevenlabs.
 */
export async function regenerateOutboundVoices(
  force = false,
  ttsProvider?: "edge" | "elevenlabs"
): Promise<Record<string, unknown>> {
  return postJson("/kb/outbound-commercial/voices/regenerate", {
    force,
    tts_provider: ttsProvider
  });
}
