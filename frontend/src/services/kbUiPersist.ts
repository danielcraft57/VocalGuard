/**
 * Persist / cache UI pour /kb et /simulator (basculement de pages plus fluide).
 *
 * - Memoire process : partage entre navigations client
 * - sessionStorage : survit au refresh / onglet
 * - TTL court sur les intents pour forcer un soft-refresh
 */

import type { KbIntent } from "./kbApi";
import type { ChatSession } from "../components/kb/chatHistory";

const INTENTS_KEY = "vg_kb_intents_cache_v1";
const KB_UI_KEY = "vg_kb_ui_state_v1";
const SIM_UI_KEY = "vg_sim_ui_state_v1";
const CHATS_KEY = "vg_kb_chats_cache_v1";

/** TTL intents en session (ms) - au-dela on refresh silencieusement. */
export const INTENTS_TTL_MS = 5 * 60 * 1000;

type IntentsCache = {
  intents: KbIntent[];
  savedAt: number;
};

export type KbUiState = {
  filterQ: string;
  groupFilter: string;
};

export type SimulatorUiState = {
  activeSessionId: string | null;
  chatInput: string;
  welcomeText?: string;
};

type ChatsCache = {
  sessions: ChatSession[];
  savedAt: number;
};

/** Cache memoire (meme onglet SPA). */
let memoryIntents: IntentsCache | null = null;
let memoryChats: ChatsCache | null = null;

function readJson<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / private mode */
  }
}

/**
 * Lit le cache intents (memoire puis session).
 *
 * @returns Cache ou null.
 */
export function loadIntentsCache(): IntentsCache | null {
  if (memoryIntents?.intents?.length) return memoryIntents;
  const fromSession = readJson<IntentsCache>(INTENTS_KEY);
  if (fromSession?.intents?.length) {
    memoryIntents = fromSession;
    return fromSession;
  }
  return null;
}

/**
 * Ecrit le cache intents.
 *
 * @param intents Liste API.
 */
export function saveIntentsCache(intents: KbIntent[]): void {
  const payload: IntentsCache = { intents, savedAt: Date.now() };
  memoryIntents = payload;
  writeJson(INTENTS_KEY, payload);
}

/**
 * True si le cache intents est encore frais.
 *
 * @param cache Cache courant.
 * @param ttlMs Duree de vie.
 */
export function isIntentsCacheFresh(
  cache: IntentsCache | null,
  ttlMs: number = INTENTS_TTL_MS
): boolean {
  if (!cache?.intents?.length) return false;
  return Date.now() - cache.savedAt < ttlMs;
}

/**
 * Etat UI page KB (filtres).
 *
 * @returns Etat ou defaut.
 */
export function loadKbUiState(): KbUiState {
  const stored = readJson<KbUiState>(KB_UI_KEY);
  return {
    filterQ: stored?.filterQ ?? "",
    groupFilter: stored?.groupFilter ?? "all"
  };
}

/**
 * Sauve filtres KB.
 *
 * @param state Filtres.
 */
export function saveKbUiState(state: KbUiState): void {
  writeJson(KB_UI_KEY, state);
}

/**
 * Etat UI simulateur (session active + brouillon).
 *
 * @returns Etat.
 */
export function loadSimulatorUiState(): SimulatorUiState {
  const stored = readJson<SimulatorUiState>(SIM_UI_KEY);
  return {
    activeSessionId: stored?.activeSessionId ?? null,
    chatInput: stored?.chatInput ?? "",
    welcomeText: stored?.welcomeText
  };
}

/**
 * Sauve etat simulateur.
 *
 * @param state Patch partiel merge.
 */
export function saveSimulatorUiState(state: Partial<SimulatorUiState>): void {
  const prev = loadSimulatorUiState();
  writeJson(SIM_UI_KEY, { ...prev, ...state });
}

/**
 * Cache sessions tchatche (memoire + session) pour affichage immediat.
 *
 * @returns Sessions ou null.
 */
export function loadChatsCache(): ChatSession[] | null {
  if (memoryChats?.sessions?.length) return memoryChats.sessions;
  const fromSession = readJson<ChatsCache>(CHATS_KEY);
  if (fromSession?.sessions?.length) {
    memoryChats = fromSession;
    return fromSession.sessions;
  }
  return null;
}

/**
 * Persiste sessions tchatche en cache session.
 *
 * @param sessions Liste.
 */
export function saveChatsCache(sessions: ChatSession[]): void {
  const payload: ChatsCache = { sessions, savedAt: Date.now() };
  memoryChats = payload;
  writeJson(CHATS_KEY, payload);
}
