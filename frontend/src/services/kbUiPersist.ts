/**
 * Persist / cache UI pour /kb et /simulator (basculement de pages plus fluide).
 *
 * - Memoire process : partage entre navigations client
 * - sessionStorage : survit au refresh / onglet
 * - TTL court sur les intents pour forcer un soft-refresh
 */

import type { KbIntent } from "./kbApi";
import type { ChatSession } from "../components/kb/chatHistory";

const INTENTS_KEY = "vg_kb_intents_cache_v2";
const KB_UI_KEY = "vg_kb_ui_state_v2";
const SIM_UI_KEY = "vg_sim_ui_state_v1";
const CHATS_KEY = "vg_kb_chats_cache_v1";

/** TTL intents en session (ms) - au-dela on refresh silencieusement. */
export const INTENTS_TTL_MS = 5 * 60 * 1000;

/** Profils catalogue KB (collections Qdrant). */
export type KbProfile = "inbound" | "outbound_commercial";

export type KbVoicePrefs = {
  tts_provider: "edge" | "elevenlabs";
  edge_tts_voice: string;
  edge_tts_rate: string;
  edge_tts_pitch: string;
  tts_voice_gain_db: number;
  elevenlabs_voice_id: string;
};

type IntentsCacheEntry = {
  intents: KbIntent[];
  savedAt: number;
};

type IntentsCacheStore = {
  byProfile: Partial<Record<KbProfile, IntentsCacheEntry>>;
};

export type KbUiState = {
  filterQ: string;
  groupFilter: string;
  profile: KbProfile;
  voiceByProfile: Partial<Record<KbProfile, KbVoicePrefs>>;
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

/** ElevenLabs Matilda (Marie commercial). */
export const ELEVENLABS_VOICE_MATILDA = "XrExE9yKIg1WjnnlVkGX";

/** Prefs voix par defaut (proche incoming-audio). */
export const DEFAULT_KB_VOICE_PREFS: KbVoicePrefs = {
  tts_provider: "edge",
  edge_tts_voice: "fr-FR-VivienneMultilingualNeural",
  edge_tts_rate: "+0%",
  edge_tts_pitch: "+0Hz",
  tts_voice_gain_db: -6,
  elevenlabs_voice_id: "JBFqnCBsd6RMkjVDRZzb"
};

/** Commercial sortant : Matilda + fallback Edge femme. */
export const DEFAULT_OUTBOUND_KB_VOICE_PREFS: KbVoicePrefs = {
  tts_provider: "elevenlabs",
  edge_tts_voice: "fr-FR-DeniseNeural",
  edge_tts_rate: "+0%",
  edge_tts_pitch: "+0Hz",
  tts_voice_gain_db: -6,
  elevenlabs_voice_id: ELEVENLABS_VOICE_MATILDA
};

/** Cache memoire (meme onglet SPA). */
let memoryIntents: IntentsCacheStore | null = null;
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
 * Prefs voix pour un profil (merge avec defauts).
 *
 * @param state Etat UI.
 * @param profile Catalogue.
 * @returns Prefs completes.
 */
export function voicePrefsForProfile(
  state: KbUiState,
  profile: KbProfile
): KbVoicePrefs {
  const base =
    profile === "outbound_commercial"
      ? DEFAULT_OUTBOUND_KB_VOICE_PREFS
      : DEFAULT_KB_VOICE_PREFS;
  const merged = { ...base, ...(state.voiceByProfile?.[profile] || {}) };
  if (
    profile === "outbound_commercial" &&
    (!merged.elevenlabs_voice_id ||
      merged.elevenlabs_voice_id === "JBFqnCBsd6RMkjVDRZzb")
  ) {
    merged.elevenlabs_voice_id = ELEVENLABS_VOICE_MATILDA;
    merged.tts_provider = "elevenlabs";
  }
  if (
    profile === "outbound_commercial" &&
    merged.edge_tts_voice.includes("Henri")
  ) {
    merged.edge_tts_voice = "fr-FR-DeniseNeural";
  }
  return merged;
}

/**
 * Lit le cache intents pour un profil (memoire puis session).
 *
 * @param profile Catalogue.
 * @returns Cache ou null.
 */
export function loadIntentsCache(profile: KbProfile): IntentsCacheEntry | null {
  const fromMem = memoryIntents?.byProfile?.[profile];
  if (fromMem?.intents?.length) return fromMem;
  const store = readJson<IntentsCacheStore>(INTENTS_KEY);
  if (store?.byProfile?.[profile]?.intents?.length) {
    memoryIntents = store;
    return store.byProfile[profile]!;
  }
  return null;
}

/**
 * Ecrit le cache intents pour un profil.
 *
 * @param profile Catalogue.
 * @param intents Liste API.
 */
export function saveIntentsCache(profile: KbProfile, intents: KbIntent[]): void {
  const prev = memoryIntents || readJson<IntentsCacheStore>(INTENTS_KEY) || { byProfile: {} };
  const payload: IntentsCacheStore = {
    byProfile: {
      ...prev.byProfile,
      [profile]: { intents, savedAt: Date.now() }
    }
  };
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
  cache: IntentsCacheEntry | null,
  ttlMs: number = INTENTS_TTL_MS
): boolean {
  if (!cache?.intents?.length) return false;
  return Date.now() - cache.savedAt < ttlMs;
}

/**
 * Etat UI page KB (filtres + profil + voix).
 *
 * @returns Etat ou defaut.
 */
export function loadKbUiState(): KbUiState {
  const stored = readJson<KbUiState>(KB_UI_KEY);
  const profile: KbProfile =
    stored?.profile === "outbound_commercial" ? "outbound_commercial" : "inbound";
  return {
    filterQ: stored?.filterQ ?? "",
    groupFilter: stored?.groupFilter ?? "all",
    profile,
    voiceByProfile: stored?.voiceByProfile ?? {}
  };
}

/**
 * Sauve etat KB.
 *
 * @param state Etat complet.
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
