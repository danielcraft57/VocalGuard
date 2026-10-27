/**
 * Panneau Tchatche (simulateur d'appel) : historique + conversation.
 */

"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Box,
  Button,
  CircularProgress,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import ChatIcon from "@mui/icons-material/Chat";
import HistoryIcon from "@mui/icons-material/History";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import CheckIcon from "@mui/icons-material/Check";
import {
  chatKb,
  deleteKbChat,
  fetchKbChats,
  fetchKbIntents,
  importKbChats,
  isAbortError,
  patchKbIntent,
  upsertKbChat,
  type KbIntent
} from "../../services/kbApi";
import {
  isIntentsCacheFresh,
  loadChatsCache,
  loadIntentsCache,
  loadSimulatorUiState,
  saveChatsCache,
  saveIntentsCache,
  saveSimulatorUiState
} from "../../services/kbUiPersist";
import { KbIntentBars } from "./KbIntentBars";
import { KbSoftSyncBar, KbTchatcheSkeleton } from "./KbSkeleton";
import {
  createSession,
  DEFAULT_CHAT_WELCOME,
  loadChatSessions,
  loadChatWelcome,
  saveChatSessions,
  saveChatWelcome,
  sessionFromDto,
  sessionToDto,
  titleFromMessages,
  type ChatMsg,
  type ChatSession
} from "./chatHistory";

/**
 * Simulateur Tchatche avec historique BDD (+ miroir local).
 *
 * @returns Panneau React.
 */
export function KbTchatchePanel(): React.ReactElement {
  const [intents, setIntents] = useState<KbIntent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [welcomeText, setWelcomeText] = useState(DEFAULT_CHAT_WELCOME);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [bubbleSaving, setBubbleSaving] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);

  useEffect(() => {
    const ui = loadSimulatorUiState();
    const welcome = ui.welcomeText || loadChatWelcome();
    setWelcomeText(welcome);
    setChatInput(ui.chatInput || "");

    const cachedChats = loadChatsCache() || loadChatSessions();
    if (cachedChats.length) {
      setSessions(cachedChats);
      if (ui.activeSessionId) {
        const found = cachedChats.find((s) => s.id === ui.activeSessionId) || null;
        setActiveSession(found);
      }
      setBootstrapping(false);
    }

    const intentCache = loadIntentsCache("inbound");
    if (intentCache?.intents?.length) {
      setIntents(intentCache.intents);
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    saveSimulatorUiState({
      activeSessionId: activeSession?.id ?? null,
      chatInput,
      welcomeText
    });
  }, [activeSession?.id, chatInput, welcomeText, hydrated]);

  useEffect(() => {
    if (!hydrated) return;
    const ac = new AbortController();
    let cancelled = false;

    void (async () => {
      const hasLocal = sessions.length > 0;
      if (hasLocal) setSyncing(true);
      else setBootstrapping(true);

      try {
        let rows = loadIntentsCache("inbound")?.intents;
        if (!rows?.length || !isIntentsCacheFresh(loadIntentsCache("inbound"))) {
          rows = await fetchKbIntents(false, ac.signal, "inbound");
          if (!ac.signal.aborted) saveIntentsCache("inbound", rows);
        }
        if (cancelled || ac.signal.aborted) return;
        setIntents(rows);
        const salutation = rows.find((i) => i.tag === "salutation");
        if (
          salutation?.responses?.[0] &&
          loadChatWelcome() === DEFAULT_CHAT_WELCOME &&
          !loadSimulatorUiState().welcomeText
        ) {
          setWelcomeText(salutation.responses[0]);
        }
      } catch (e) {
        if (isAbortError(e) || ac.signal.aborted) return;
        /* intents optionnels pour edition bulle */
      }

      try {
        const local = loadChatSessions();
        if (local.length > 0) {
          await importKbChats(local.map(sessionToDto), ac.signal);
          if (ac.signal.aborted) return;
          try {
            localStorage.removeItem("vg_kb_chat_history_v1");
          } catch {
            /* ignore */
          }
        }
        const remote = await fetchKbChats(30, ac.signal);
        if (cancelled || ac.signal.aborted) return;
        const mapped = remote.map(sessionFromDto);
        setSessions(mapped);
        saveChatsCache(mapped);
        saveChatSessions(mapped);
        const ui = loadSimulatorUiState();
        if (ui.activeSessionId) {
          const found = mapped.find((s) => s.id === ui.activeSessionId);
          if (found) setActiveSession(found);
        }
      } catch (e) {
        if (isAbortError(e) || ac.signal.aborted) return;
        if (!cancelled) {
          const fallback = loadChatSessions();
          setSessions(fallback);
          saveChatsCache(fallback);
        }
      } finally {
        if (!cancelled && !ac.signal.aborted) {
          setBootstrapping(false);
          setSyncing(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      ac.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- hydrate once
  }, [hydrated]);

  const persistToDb = useCallback(async (session: ChatSession) => {
    try {
      await upsertKbChat(sessionToDto(session));
    } catch {
      const locals = loadChatSessions();
      saveChatSessions([session, ...locals.filter((s) => s.id !== session.id)]);
    }
  }, []);

  const persistSessions = useCallback((next: ChatSession[]) => {
    setSessions(next);
    saveChatSessions(next);
    saveChatsCache(next);
  }, []);

  const upsertActive = useCallback(
    (session: ChatSession) => {
      setActiveSession(session);
      setSessions((prev) => {
        const next = [session, ...prev.filter((s) => s.id !== session.id)];
        saveChatSessions(next);
        saveChatsCache(next);
        return next;
      });
      void persistToDb(session);
    },
    [persistToDb]
  );

  const openNewConversation = useCallback(() => {
    const session = createSession(welcomeText.trim() || DEFAULT_CHAT_WELCOME);
    stickToBottomRef.current = true;
    setActiveSession(session);
    setChatInput("");
    setEditingMsgId(null);
    persistSessions([session, ...sessions.filter((s) => s.id !== session.id)]);
    void persistToDb(session);
  }, [welcomeText, sessions, persistSessions, persistToDb]);

  const openHistorySession = useCallback((session: ChatSession) => {
    stickToBottomRef.current = false;
    setActiveSession(session);
    setChatInput("");
    setEditingMsgId(null);
  }, []);

  const deleteSession = useCallback(
    (id: string) => {
      const next = sessions.filter((s) => s.id !== id);
      persistSessions(next);
      void deleteKbChat(id).catch(() => {
        /* ignore */
      });
      if (activeSession?.id === id) {
        setActiveSession(null);
      }
    },
    [sessions, persistSessions, activeSession]
  );

  const scrollIfNeeded = useCallback(() => {
    if (!stickToBottomRef.current) return;
    const el = chatScrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, []);

  useEffect(() => {
    if (!activeSession) return;
    const t = window.setTimeout(scrollIfNeeded, 50);
    return () => window.clearTimeout(t);
  }, [activeSession?.messages.length, activeSession?.id, scrollIfNeeded]);

  const sendChat = useCallback(async () => {
    if (!activeSession) return;
    const text = chatInput.trim();
    if (!text || chatBusy) return;
    setChatBusy(true);
    setError(null);
    setChatInput("");
    stickToBottomRef.current = true;

    const userMsg: ChatMsg = { id: `u-${Date.now()}`, role: "user", text };
    let working: ChatSession = {
      ...activeSession,
      messages: [...activeSession.messages, userMsg],
      updatedAt: new Date().toISOString()
    };
    setActiveSession(working);

    try {
      const r = await chatKb(
        text,
        working.recentReplies,
        working.recentTags,
        working.recentUserTexts || []
      );
      const botMsg: ChatMsg = {
        id: `b-${Date.now()}`,
        role: "bot",
        text: r.reply,
        tag: r.tag,
        score: r.score,
        preds: r.top_predictions?.slice(0, 5) || [],
        responseIndex: typeof r.response_index === "number" ? r.response_index : 0,
        personaReason: r.persona_reason || null,
        moodTone: r.mood?.tone || null,
        engine: r.source || null
      };
      working = {
        ...working,
        title: titleFromMessages([...working.messages, botMsg]),
        messages: [...working.messages, botMsg],
        recentReplies: r.reply
          ? [...working.recentReplies, r.reply].slice(-12)
          : working.recentReplies,
        recentTags: r.tag
          ? [...working.recentTags, r.tag].slice(-12)
          : working.recentTags,
        recentUserTexts: [...(working.recentUserTexts || []), text].slice(-12),
        updatedAt: new Date().toISOString()
      };
      upsertActive(working);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur tchat");
      working = {
        ...working,
        messages: [
          ...working.messages,
          {
            id: `e-${Date.now()}`,
            role: "bot",
            text: "Oups, le tchat a plante. Reessaie dans un instant."
          }
        ],
        updatedAt: new Date().toISOString()
      };
      upsertActive(working);
    } finally {
      setChatBusy(false);
    }
  }, [activeSession, chatInput, chatBusy, upsertActive]);

  const startEditBubble = useCallback((msg: ChatMsg) => {
    if (msg.role !== "bot") return;
    setEditingMsgId(msg.id);
    setEditDraft(msg.text);
  }, []);

  const cancelEditBubble = useCallback(() => {
    setEditingMsgId(null);
    setEditDraft("");
  }, []);

  const reloadIntents = useCallback(async () => {
    try {
      const rows = await fetchKbIntents(false, undefined, "inbound");
      setIntents(rows);
      saveIntentsCache("inbound", rows);
    } catch {
      /* ignore */
    }
  }, []);

  const saveBubbleEdit = useCallback(async () => {
    if (!activeSession || !editingMsgId) return;
    const msg = activeSession.messages.find((m) => m.id === editingMsgId);
    if (!msg || msg.role !== "bot") return;
    const nextText = editDraft.trim();
    if (!nextText) return;

    setBubbleSaving(true);
    setError(null);
    try {
      if (msg.id === "welcome" || (!msg.tag && msg.id.startsWith("welcome"))) {
        saveChatWelcome(nextText);
        setWelcomeText(nextText);
        const salutation = intents.find((i) => i.tag === "salutation");
        if (salutation) {
          const responses = [...salutation.responses];
          if (responses.length === 0) responses.push(nextText);
          else responses[0] = nextText;
          await patchKbIntent("salutation", { responses });
          await reloadIntents();
        }
      } else if (msg.tag) {
        const intent = intents.find((i) => i.tag === msg.tag);
        if (intent) {
          const responses = [...intent.responses];
          const idx =
            typeof msg.responseIndex === "number" && msg.responseIndex >= 0
              ? msg.responseIndex
              : 0;
          if (responses.length === 0) {
            responses.push(nextText);
          } else if (idx < responses.length) {
            responses[idx] = nextText;
          } else {
            responses[0] = nextText;
          }
          await patchKbIntent(msg.tag, { responses });
          await reloadIntents();
        }
      }

      const messages = activeSession.messages.map((m) =>
        m.id === editingMsgId ? { ...m, text: nextText } : m
      );
      upsertActive({
        ...activeSession,
        messages,
        updatedAt: new Date().toISOString()
      });
      setEditingMsgId(null);
      setEditDraft("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur sauvegarde bulle");
    } finally {
      setBubbleSaving(false);
    }
  }, [
    activeSession,
    editingMsgId,
    editDraft,
    intents,
    reloadIntents,
    upsertActive
  ]);

  const saveWelcomeSetting = useCallback(async () => {
    const text = welcomeText.trim() || DEFAULT_CHAT_WELCOME;
    saveChatWelcome(text);
    setWelcomeText(text);
    setError(null);
    try {
      const salutation = intents.find((i) => i.tag === "salutation");
      if (salutation) {
        const responses = [...salutation.responses];
        if (responses.length === 0) responses.push(text);
        else responses[0] = text;
        await patchKbIntent("salutation", { responses });
        await reloadIntents();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur sauvegarde accueil");
    }
  }, [welcomeText, intents, reloadIntents]);

  if (bootstrapping && sessions.length === 0) {
    return (
      <Stack spacing={1.5}>
        <KbSoftSyncBar label="Chargement du simulateur…" />
        <KbTchatcheSkeleton />
      </Stack>
    );
  }

  return (
    <Stack spacing={2}>
      {syncing ? (
        <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
          <KbSoftSyncBar label="Synchro historique…" />
        </Box>
      ) : null}
      {error ? (
        <Typography color="error" variant="body2">
          {error}
        </Typography>
      ) : null}

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "280px 1fr" },
          gap: 2,
          alignItems: "stretch",
          minHeight: { md: "70vh" }
        }}
      >
        {/* Historique */}
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2,
            bgcolor: "background.paper",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            maxHeight: { xs: 280, md: "none" }
          }}
        >
          <Stack
            direction="row"
            spacing={1}
            sx={{
              alignItems: "center",
              px: 1.5,
              py: 1.25,
              borderBottom: "1px solid",
              borderColor: "divider"
            }}
          >
            <HistoryIcon fontSize="small" color="action" />
            <Typography variant="subtitle2" sx={{ flex: 1 }}>
              Historique
            </Typography>
            <Button
              size="small"
              variant="contained"
              startIcon={<ChatIcon />}
              onClick={openNewConversation}
            >
              Nouvelle
            </Button>
          </Stack>
          <Box sx={{ flex: 1, overflowY: "auto" }}>
            {sessions.length === 0 ? (
              <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
                Aucune conversation pour l&apos;instant.
              </Typography>
            ) : (
              sessions.map((s) => (
                <Stack
                  key={s.id}
                  direction="row"
                  sx={{
                    alignItems: "center",
                    px: 1.5,
                    py: 1,
                    borderBottom: "1px solid",
                    borderColor: "divider",
                    cursor: "pointer",
                    bgcolor:
                      activeSession?.id === s.id ? "action.selected" : "transparent",
                    "&:hover": { bgcolor: "action.hover" }
                  }}
                  onClick={() => openHistorySession(s)}
                >
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="body2" noWrap>
                      {s.title}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {new Date(s.updatedAt).toLocaleString("fr-FR")}
                    </Typography>
                  </Box>
                  <IconButton
                    size="small"
                    aria-label="supprimer"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteSession(s.id);
                    }}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
              ))
            )}
          </Box>
        </Box>

        {/* Conversation */}
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2,
            bgcolor: "background.paper",
            display: "flex",
            flexDirection: "column",
            minHeight: { xs: 420, md: 0 },
            overflow: "hidden"
          }}
        >
          <Stack
            direction="row"
            sx={{
              alignItems: "center",
              justifyContent: "space-between",
              px: 2,
              py: 1.25,
              borderBottom: "1px solid",
              borderColor: "divider"
            }}
          >
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Tchatche
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {activeSession
                  ? activeSession.title
                  : "Ouvre une conversation ou reprends l'historique"}
              </Typography>
            </Box>
            {!activeSession ? (
              <Button
                size="small"
                variant="outlined"
                startIcon={<ChatIcon />}
                onClick={openNewConversation}
              >
                Demarrer
              </Button>
            ) : null}
          </Stack>

          <Box
            ref={chatScrollRef}
            onScroll={(e) => {
              const el = e.currentTarget;
              stickToBottomRef.current =
                el.scrollHeight - el.scrollTop - el.clientHeight < 80;
            }}
            sx={{
              flex: 1,
              overflowY: "auto",
              p: 2,
              bgcolor: "action.hover"
            }}
          >
            {!activeSession ? (
              <Typography variant="body2" color="text.secondary">
                Clique &quot;Nouvelle&quot; pour simuler un appelant, ou choisis une
                conversation dans l&apos;historique.
              </Typography>
            ) : (
              <Stack spacing={1.25}>
                {activeSession.messages.map((m) => (
                  <Box
                    key={m.id}
                    sx={{
                      alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                      maxWidth: "92%"
                    }}
                  >
                    <Box
                      sx={{
                        px: 1.5,
                        py: 1,
                        borderRadius: 1,
                        bgcolor:
                          m.role === "user" ? "primary.main" : "background.paper",
                        color:
                          m.role === "user" ? "primary.contrastText" : "text.primary",
                        border: m.role === "bot" ? "1px solid" : "none",
                        borderColor: "divider"
                      }}
                    >
                      {editingMsgId === m.id ? (
                        <Stack spacing={1}>
                          <TextField
                            size="small"
                            fullWidth
                            multiline
                            minRows={2}
                            value={editDraft}
                            onChange={(e) => setEditDraft(e.target.value)}
                            autoFocus
                          />
                          <Stack direction="row" spacing={1}>
                            <Button
                              size="small"
                              variant="contained"
                              startIcon={<CheckIcon />}
                              disabled={bubbleSaving || !editDraft.trim()}
                              onClick={() => void saveBubbleEdit()}
                            >
                              Sauver
                            </Button>
                            <Button
                              size="small"
                              onClick={cancelEditBubble}
                              disabled={bubbleSaving}
                            >
                              Annuler
                            </Button>
                          </Stack>
                        </Stack>
                      ) : (
                        <>
                          <Typography variant="body2">{m.text}</Typography>
                          {m.role === "bot" ? (
                            <Stack
                              direction="row"
                              spacing={1}
                              sx={{
                                mt: 0.75,
                                alignItems: "center",
                                justifyContent: "space-between"
                              }}
                            >
                              <Typography variant="caption" color="text.secondary">
                                {[
                                  m.tag
                                    ? `intent: ${m.tag}${
                                        typeof m.score === "number"
                                          ? ` (${Math.round(m.score * 100)}%)`
                                          : ""
                                      }`
                                    : m.id === "welcome"
                                      ? "accueil"
                                      : "",
                                  m.moodTone ? `ton: ${m.moodTone}` : "",
                                  m.engine ? `moteur: ${m.engine}` : ""
                                ]
                                  .filter(Boolean)
                                  .join(" · ")}
                              </Typography>
                              <Tooltip title="Modifier cette reponse">
                                <IconButton
                                  size="small"
                                  aria-label="editer bulle"
                                  onClick={() => startEditBubble(m)}
                                >
                                  <EditIcon fontSize="inherit" />
                                </IconButton>
                              </Tooltip>
                            </Stack>
                          ) : null}
                        </>
                      )}
                    </Box>
                    {m.preds && m.preds.length > 0 && editingMsgId !== m.id ? (
                      <KbIntentBars preds={m.preds} winner={m.tag} animKey={m.id} />
                    ) : null}
                  </Box>
                ))}
              </Stack>
            )}
          </Box>

          <Box sx={{ p: 1.5, borderTop: "1px solid", borderColor: "divider" }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField
                fullWidth
                size="small"
                label="Ce que dit l'appelant"
                placeholder="ex. je veux un devis"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void sendChat();
                  }
                }}
                disabled={chatBusy || !activeSession}
              />
              <Button
                variant="contained"
                endIcon={
                  chatBusy ? (
                    <CircularProgress size={16} color="inherit" />
                  ) : (
                    <SendIcon />
                  )
                }
                onClick={() => void sendChat()}
                disabled={chatBusy || !chatInput.trim() || !activeSession}
              >
                Envoyer
              </Button>
            </Stack>
          </Box>
        </Box>
      </Box>

      <Box
        sx={{
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 2,
          p: 2,
          bgcolor: "background.paper"
        }}
      >
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Message d&apos;accueil
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <TextField
            label="1ere bulle (salutation)"
            size="small"
            fullWidth
            multiline
            minRows={2}
            value={welcomeText}
            onChange={(e) => setWelcomeText(e.target.value)}
          />
          <Button
            variant="outlined"
            onClick={() => void saveWelcomeSetting()}
            sx={{ flexShrink: 0, alignSelf: { sm: "flex-start" } }}
          >
            Enregistrer
          </Button>
        </Stack>
      </Box>
    </Stack>
  );
}
