/**
 * Historique local des conversations KB (tchatche).
 */

import type { KbPredictItem } from "../../services/kbApi";

const STORAGE_KEY = "vg_kb_chat_history_v1";
const WELCOME_KEY = "vg_kb_chat_welcome_v1";

export const DEFAULT_CHAT_WELCOME =
  "Bonjour, vous etes bien sur la messagerie. Comment puis-je vous aider ?";

export type ChatMsg = {
  id: string;
  role: "user" | "bot";
  text: string;
  tag?: string | null;
  score?: number;
  preds?: KbPredictItem[];
  /** Index de variante de reponse (pour patch inline). */
  responseIndex?: number;
  personaReason?: string | null;
  moodTone?: string | null;
};

export type ChatSession = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMsg[];
  recentReplies: string[];
  recentTags: string[];
  recentUserTexts: string[];
};

type Store = {
  sessions: ChatSession[];
};

/**
 * Charge le message d'accueil du tchat (local).
 *
 * @returns Texte.
 */
export function loadChatWelcome(): string {
  if (typeof window === "undefined") return DEFAULT_CHAT_WELCOME;
  try {
    const raw = localStorage.getItem(WELCOME_KEY);
    const t = (raw || "").trim();
    return t || DEFAULT_CHAT_WELCOME;
  } catch {
    return DEFAULT_CHAT_WELCOME;
  }
}

/**
 * Sauve le message d'accueil du tchat.
 *
 * @param text Texte.
 */
export function saveChatWelcome(text: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(WELCOME_KEY, text.trim() || DEFAULT_CHAT_WELCOME);
  } catch {
    /* ignore */
  }
}

/**
 * Lit l'historique des sessions.
 *
 * @returns Sessions (plus recent en tete).
 */
export function loadChatSessions(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Store;
    const sessions = Array.isArray(parsed.sessions) ? parsed.sessions : [];
    return sessions
      .map((s) => ({
        ...s,
        recentUserTexts: Array.isArray(s.recentUserTexts) ? s.recentUserTexts : [],
        recentReplies: Array.isArray(s.recentReplies) ? s.recentReplies : [],
        recentTags: Array.isArray(s.recentTags) ? s.recentTags : []
      }))
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  } catch {
    return [];
  }
}

/**
 * Persiste les sessions (cap 30).
 *
 * @param sessions Liste.
 */
export function saveChatSessions(sessions: ChatSession[]): void {
  if (typeof window === "undefined") return;
  try {
    const capped = sessions
      .slice()
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, 30);
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ sessions: capped }));
  } catch {
    /* ignore */
  }
}

/**
 * Titre court a partir des premiers messages utilisateur.
 *
 * @param messages Messages.
 * @returns Titre.
 */
export function titleFromMessages(messages: ChatMsg[]): string {
  const firstUser = messages.find((m) => m.role === "user");
  if (firstUser?.text) {
    const t = firstUser.text.trim();
    return t.length > 48 ? `${t.slice(0, 45)}…` : t;
  }
  return "Conversation";
}

/**
 * Convertit une session API → type UI.
 *
 * @param dto Payload API.
 * @returns ChatSession.
 */
export function sessionFromDto(dto: {
  id: string;
  title?: string;
  messages?: ChatMsg[];
  recentReplies?: string[];
  recentTags?: string[];
  recentUserTexts?: string[];
  createdAt?: string | null;
  updatedAt?: string | null;
}): ChatSession {
  return {
    id: dto.id,
    title: dto.title || "Conversation",
    createdAt: dto.createdAt || new Date().toISOString(),
    updatedAt: dto.updatedAt || new Date().toISOString(),
    messages: Array.isArray(dto.messages) ? (dto.messages as ChatMsg[]) : [],
    recentReplies: Array.isArray(dto.recentReplies) ? dto.recentReplies : [],
    recentTags: Array.isArray(dto.recentTags) ? dto.recentTags : [],
    recentUserTexts: Array.isArray(dto.recentUserTexts) ? dto.recentUserTexts : []
  };
}

/**
 * Convertit une session UI → DTO API.
 *
 * @param session Session locale.
 */
export function sessionToDto(session: ChatSession): {
  id: string;
  title: string;
  messages: ChatMsg[];
  recentReplies: string[];
  recentTags: string[];
  recentUserTexts: string[];
  createdAt: string;
  updatedAt: string;
} {
  return {
    id: session.id,
    title: session.title,
    messages: session.messages,
    recentReplies: session.recentReplies,
    recentTags: session.recentTags,
    recentUserTexts: session.recentUserTexts || [],
    createdAt: session.createdAt,
    updatedAt: session.updatedAt
  };
}

/**
 * Cree une nouvelle session avec le message d'accueil.
 *
 * @param welcome Texte bot initial.
 * @returns Session.
 */
export function createSession(welcome: string): ChatSession {
  const now = new Date().toISOString();
  const welcomeText = welcome.trim() || DEFAULT_CHAT_WELCOME;
  return {
    id: `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    title: "Nouvelle conversation",
    createdAt: now,
    updatedAt: now,
    messages: [
      {
        id: "welcome",
        role: "bot",
        text: welcomeText,
        tag: "salutation",
        responseIndex: 0
      }
    ],
    // L'accueil compte deja comme un tour salutation → evite le double bonjour catalogue
    recentReplies: [welcomeText],
    recentTags: ["salutation"],
    recentUserTexts: []
  };
}
