"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  InputAdornment,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import SendIcon from "@mui/icons-material/Send";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ChatIcon from "@mui/icons-material/Chat";
import HistoryIcon from "@mui/icons-material/History";
import SearchIcon from "@mui/icons-material/Search";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import { AppLayout } from "../../components/AppLayout";
import { KbIntentBars } from "../../components/kb/KbIntentBars";
import { VgPageHeader } from "../../components/mui/VgPageHeader";
import { VgSettingsSection } from "../../components/mui/VgSettingsSection";
import {
  chatKb,
  createKbIntent,
  deleteKbIntent,
  fetchKbIntents,
  getKbIntentVoiceUrl,
  patchKbIntent,
  regenerateKbVoices,
  type KbIntent
} from "../../services/kbApi";
import {
  createSession,
  DEFAULT_CHAT_WELCOME,
  loadChatSessions,
  loadChatWelcome,
  saveChatSessions,
  saveChatWelcome,
  titleFromMessages,
  type ChatMsg,
  type ChatSession
} from "./chatHistory";
import {
  groupIntents,
  INTENT_GROUPS,
  type IntentGroupId
} from "./intentGroups";

type IntentForm = {
  tag: string;
  patternsText: string;
  responsesText: string;
  priority: string;
  action: string;
  enabled: boolean;
};

/**
 * Formulaire vide pour creer un intent.
 *
 * @returns Etat initial.
 */
function emptyForm(): IntentForm {
  return {
    tag: "",
    patternsText: "",
    responsesText: "",
    priority: "10",
    action: "",
    enabled: true
  };
}

/**
 * Remplit le formulaire depuis un intent existant.
 *
 * @param row Intent.
 * @returns Formulaire.
 */
function formFromIntent(row: KbIntent): IntentForm {
  return {
    tag: row.tag,
    patternsText: row.patterns.join("\n"),
    responsesText: row.responses.join("\n"),
    priority: String(row.priority),
    action: row.action || "",
    enabled: row.enabled
  };
}

/**
 * Decoupe un textarea multi-lignes en liste non vide.
 *
 * @param text Contenu.
 * @returns Lignes nettoyees.
 */
function linesOf(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
}

/**
 * Page Base de connaissances : tchat modal + historique + intents groupes.
 */
export default function KnowledgeBasePage(): React.ReactElement {
  const [intents, setIntents] = useState<KbIntent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [regenBusy, setRegenBusy] = useState(false);
  const [regenMsg, setRegenMsg] = useState<string | null>(null);

  const [filterQ, setFilterQ] = useState("");
  const [groupFilter, setGroupFilter] = useState<IntentGroupId | "all">("all");

  const [welcomeText, setWelcomeText] = useState(DEFAULT_CHAT_WELCOME);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [chatOpen, setChatOpen] = useState(false);
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [bubbleSaving, setBubbleSaving] = useState(false);

  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editTag, setEditTag] = useState<string | null>(null);
  const [form, setForm] = useState<IntentForm>(emptyForm());
  const [saving, setSaving] = useState(false);
  const [deleteTag, setDeleteTag] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    setWelcomeText(loadChatWelcome());
    setSessions(loadChatSessions());
  }, []);

  const persistSessions = useCallback((next: ChatSession[]) => {
    setSessions(next);
    saveChatSessions(next);
  }, []);

  const upsertActive = useCallback((session: ChatSession) => {
    setActiveSession(session);
    setSessions((prev) => {
      const next = [session, ...prev.filter((s) => s.id !== session.id)];
      saveChatSessions(next);
      return next;
    });
  }, []);

  const playVoice = useCallback((tag: string) => {
    const url = getKbIntentVoiceUrl(tag);
    if (!audioRef.current) audioRef.current = new Audio();
    const el = audioRef.current;
    el.src = url;
    void el.play().catch(() => {
      setError(`Lecture impossible pour ${tag} (WAV manquant ?)`);
    });
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchKbIntents(false);
      setIntents(rows);
      const salutation = rows.find((i) => i.tag === "salutation");
      if (salutation?.responses?.[0] && loadChatWelcome() === DEFAULT_CHAT_WELCOME) {
        // Prefill accueil depuis l'intent salutation si jamais personnalise
        setWelcomeText(salutation.responses[0]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur chargement KB");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const grouped = useMemo(
    () => groupIntents(intents, filterQ, groupFilter),
    [intents, filterQ, groupFilter]
  );

  const openNewConversation = useCallback(() => {
    const session = createSession(welcomeText.trim() || DEFAULT_CHAT_WELCOME);
    stickToBottomRef.current = true;
    setActiveSession(session);
    setChatInput("");
    setEditingMsgId(null);
    setChatOpen(true);
    persistSessions([session, ...sessions.filter((s) => s.id !== session.id)]);
  }, [welcomeText, sessions, persistSessions]);

  const openHistorySession = useCallback((session: ChatSession) => {
    stickToBottomRef.current = false;
    setActiveSession(session);
    setChatInput("");
    setEditingMsgId(null);
    setChatOpen(true);
  }, []);

  const closeChat = useCallback(() => {
    if (activeSession) {
      const updated: ChatSession = {
        ...activeSession,
        title: titleFromMessages(activeSession.messages),
        updatedAt: new Date().toISOString()
      };
      const others = sessions.filter((s) => s.id !== updated.id);
      persistSessions([updated, ...others]);
    }
    setChatOpen(false);
    setEditingMsgId(null);
  }, [activeSession, sessions, persistSessions]);

  const scrollIfNeeded = useCallback(() => {
    if (!stickToBottomRef.current) return;
    const el = chatScrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, []);

  useEffect(() => {
    if (!chatOpen) return;
    // Uniquement si l'utilisateur vient d'envoyer (pas a chaque rendu / historique)
    const t = window.setTimeout(scrollIfNeeded, 50);
    return () => window.clearTimeout(t);
  }, [activeSession?.messages.length, chatOpen, scrollIfNeeded]);

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
        moodTone: r.mood?.tone || null
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

  const saveBubbleEdit = useCallback(async () => {
    if (!activeSession || !editingMsgId) return;
    const msg = activeSession.messages.find((m) => m.id === editingMsgId);
    if (!msg || msg.role !== "bot") return;
    const nextText = editDraft.trim();
    if (!nextText) return;

    setBubbleSaving(true);
    setError(null);
    try {
      // Message d'accueil (1ere bulle) → pref locale + intent salutation si possible
      if (msg.id === "welcome" || (!msg.tag && msg.id.startsWith("welcome"))) {
        saveChatWelcome(nextText);
        setWelcomeText(nextText);
        const salutation = intents.find((i) => i.tag === "salutation");
        if (salutation) {
          const responses = [...salutation.responses];
          if (responses.length === 0) responses.push(nextText);
          else responses[0] = nextText;
          await patchKbIntent("salutation", { responses });
          await load();
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
            // Variante pont (index -1) : remplace la 1ere pour rester coherent
            responses[0] = nextText;
          }
          await patchKbIntent(msg.tag, { responses });
          await load();
        }
      }

      const messages = activeSession.messages.map((m) =>
        m.id === editingMsgId ? { ...m, text: nextText } : m
      );
      const updated: ChatSession = {
        ...activeSession,
        messages,
        updatedAt: new Date().toISOString()
      };
      upsertActive(updated);
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
    load,
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
        await load();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur sauvegarde accueil");
    }
  }, [welcomeText, intents, load]);

  const openCreate = useCallback(() => {
    setEditTag(null);
    setForm(emptyForm());
    setDialogOpen(true);
  }, []);

  const openEdit = useCallback((row: KbIntent) => {
    setEditTag(row.tag);
    setForm(formFromIntent(row));
    setDialogOpen(true);
  }, []);

  const saveIntent = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      const patterns = linesOf(form.patternsText);
      const responses = linesOf(form.responsesText);
      const priority = Math.max(0, Math.min(100, parseInt(form.priority, 10) || 10));
      const action = form.action.trim() || null;
      if (editTag) {
        await patchKbIntent(editTag, {
          patterns,
          responses,
          priority,
          enabled: form.enabled,
          action: action || undefined,
          clear_action: !action
        });
      } else {
        const tag = form.tag.trim().toLowerCase();
        if (!tag) throw new Error("Le tag est obligatoire");
        if (!responses.length) throw new Error("Au moins une reponse");
        await createKbIntent({
          tag,
          patterns,
          responses,
          priority,
          enabled: form.enabled,
          action
        });
      }
      setDialogOpen(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur sauvegarde");
    } finally {
      setSaving(false);
    }
  }, [editTag, form, load]);

  const confirmDelete = useCallback(async () => {
    if (!deleteTag) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteKbIntent(deleteTag);
      setDeleteTag(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur suppression");
    } finally {
      setDeleting(false);
    }
  }, [deleteTag, load]);

  const runRegen = useCallback(async () => {
    setRegenBusy(true);
    setRegenMsg(null);
    try {
      const r = await regenerateKbVoices(true);
      setRegenMsg(`Voix: ${r.ok} ok, ${r.skipped} ignorees, ${r.failed} echecs`);
    } catch (e) {
      setRegenMsg(e instanceof Error ? e.message : "Echec regen");
    } finally {
      setRegenBusy(false);
    }
  }, []);

  const deleteSession = useCallback(
    (id: string) => {
      persistSessions(sessions.filter((s) => s.id !== id));
      if (activeSession?.id === id) {
        setActiveSession(null);
        setChatOpen(false);
      }
    },
    [sessions, persistSessions, activeSession]
  );

  return (
    <AppLayout title="Base de connaissances" hidePageHeader>
      <VgPageHeader
        title="Base de connaissances"
        subtitle="Tchatche en modale, historique, intents par groupes. Edite les reponses dans les bulles."
        action={
          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
            <Button
              component={Link}
              href="/settings/incoming-audio"
              size="small"
              variant="outlined"
            >
              Voix d'accueil
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={() => void load()}
              disabled={loading}
            >
              Actualiser
            </Button>
            <Button size="small" variant="outlined" startIcon={<AddIcon />} onClick={openCreate}>
              Nouvel intent
            </Button>
            <Button
              size="small"
              variant="contained"
              startIcon={<RecordVoiceOverIcon />}
              onClick={() => void runRegen()}
              disabled={regenBusy}
            >
              Regenerer les voix
            </Button>
          </Stack>
        }
      />

      {error ? (
        <Typography color="error" sx={{ mb: 2 }}>
          {error}
        </Typography>
      ) : null}
      {regenMsg ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {regenMsg}
        </Typography>
      ) : null}

      <VgSettingsSection
        title="Tchatche"
        description="Ouvre une conversation dans une modale. Plus de scroll sauvage sur la page. Clique une bulle bot pour editer la reponse."
      >
        <Stack spacing={2}>
          <TextField
            label="Message d'accueil (1ere bulle)"
            size="small"
            fullWidth
            multiline
            minRows={2}
            value={welcomeText}
            onChange={(e) => setWelcomeText(e.target.value)}
            helperText="Aussi synchronise avec l'intent salutation (1ere reponse)."
          />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <Button variant="outlined" onClick={() => void saveWelcomeSetting()}>
              Enregistrer l'accueil
            </Button>
            <Button
              variant="contained"
              startIcon={<ChatIcon />}
              onClick={openNewConversation}
            >
              Ouvrir une nlle conversation
            </Button>
          </Stack>

          <Box>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}>
              <HistoryIcon fontSize="small" color="action" />
              <Typography variant="subtitle2">Historique</Typography>
            </Stack>
            {sessions.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Aucune conversation pour l'instant.
              </Typography>
            ) : (
              <Stack
                spacing={0}
                sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, overflow: "hidden" }}
              >
                {sessions.slice(0, 12).map((s) => (
                  <Stack
                    key={s.id}
                    direction="row"
                    sx={{
                      alignItems: "center",
                      px: 1.5,
                      py: 1,
                      borderBottom: "1px solid",
                      borderColor: "divider",
                      "&:last-child": { borderBottom: "none" },
                      cursor: "pointer",
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
                ))}
              </Stack>
            )}
          </Box>
        </Stack>
      </VgSettingsSection>

      <VgSettingsSection
        title={`Intents (${intents.length})`}
        description="Filtres + groupes. Plus de tableau interminable."
      >
        <Stack spacing={1.5} sx={{ mb: 2 }}>
          <TextField
            size="small"
            fullWidth
            placeholder="Filtrer (tag, pattern, reponse…)"
            value={filterQ}
            onChange={(e) => setFilterQ(e.target.value)}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                )
              }
            }}
          />
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: "wrap", gap: 0.75 }}>
            <Chip
              size="small"
              label="Tous"
              color={groupFilter === "all" ? "primary" : "default"}
              onClick={() => setGroupFilter("all")}
              variant={groupFilter === "all" ? "filled" : "outlined"}
            />
            {INTENT_GROUPS.map((g) => (
              <Chip
                key={g.id}
                size="small"
                label={g.label}
                color={groupFilter === g.id ? "primary" : "default"}
                onClick={() => setGroupFilter(g.id)}
                variant={groupFilter === g.id ? "filled" : "outlined"}
              />
            ))}
          </Stack>
        </Stack>

        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          INTENT_GROUPS.map((g) => {
            const rows = grouped[g.id];
            if (!rows.length) return null;
            return (
              <Accordion
                key={g.id}
                defaultExpanded={g.id === "accueil" || groupFilter === g.id}
                disableGutters
                elevation={0}
                sx={{
                  border: 1,
                  borderColor: "divider",
                  borderRadius: 1,
                  mb: 1,
                  "&:before": { display: "none" }
                }}
              >
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Stack spacing={0.25}>
                    <Typography variant="subtitle2">
                      {g.label}{" "}
                      <Typography component="span" variant="caption" color="text.secondary">
                        ({rows.length})
                      </Typography>
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {g.hint}
                    </Typography>
                  </Stack>
                </AccordionSummary>
                <AccordionDetails sx={{ pt: 0 }}>
                  <Stack spacing={1}>
                    {rows.map((row) => (
                      <Box
                        key={row.tag}
                        sx={{
                          p: 1.25,
                          borderRadius: 1,
                          border: "1px solid",
                          borderColor: "divider",
                          bgcolor: "background.paper"
                        }}
                      >
                        <Stack
                          direction={{ xs: "column", sm: "row" }}
                          spacing={1}
                          sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
                        >
                          <Box sx={{ minWidth: 0, flex: 1 }}>
                            <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mb: 0.5 }}>
                              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                {row.tag}
                              </Typography>
                              {!row.enabled ? <Chip size="small" label="off" /> : null}
                              {row.action ? (
                                <Chip size="small" variant="outlined" label={row.action} />
                              ) : null}
                              <Chip size="small" variant="outlined" label={`prio ${row.priority}`} />
                            </Stack>
                            <Typography variant="body2" color="text.secondary" noWrap title={row.responses[0] || ""}>
                              {row.responses[0] || "—"}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {row.patterns.length} patterns · {row.responses.length} reponse
                              {row.responses.length > 1 ? "s" : ""}
                            </Typography>
                          </Box>
                          <Stack direction="row" spacing={0.5} sx={{ flexShrink: 0 }}>
                            <Button
                              size="small"
                              startIcon={<PlayArrowIcon />}
                              disabled={!row.has_wav}
                              onClick={() => playVoice(row.tag)}
                            >
                              {row.has_wav ? "Ecouter" : "Absent"}
                            </Button>
                            <IconButton size="small" aria-label="modifier" onClick={() => openEdit(row)}>
                              <EditIcon fontSize="small" />
                            </IconButton>
                            <IconButton
                              size="small"
                              aria-label="supprimer"
                              color="error"
                              onClick={() => setDeleteTag(row.tag)}
                            >
                              <DeleteIcon fontSize="small" />
                            </IconButton>
                          </Stack>
                        </Stack>
                      </Box>
                    ))}
                  </Stack>
                </AccordionDetails>
              </Accordion>
            );
          })
        )}
      </VgSettingsSection>

      <Dialog
        open={chatOpen}
        onClose={closeChat}
        fullWidth
        maxWidth="md"
        slotProps={{ paper: { sx: { height: { xs: "90vh", sm: "80vh" } } } }}
      >
        <DialogTitle sx={{ pr: 1 }}>
          <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between" }}>
            <Box>
              <Typography variant="h6" component="span">
                Tchatche
              </Typography>
              {activeSession ? (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                  {activeSession.title}
                </Typography>
              ) : null}
            </Box>
            <IconButton aria-label="fermer" onClick={closeChat}>
              <CloseIcon />
            </IconButton>
          </Stack>
        </DialogTitle>
        <DialogContent
          dividers
          sx={{ display: "flex", flexDirection: "column", p: 0, minHeight: 0 }}
        >
          <Box
            ref={chatScrollRef}
            onScroll={(e) => {
              const el = e.currentTarget;
              const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
              stickToBottomRef.current = nearBottom;
            }}
            sx={{
              flex: 1,
              overflowY: "auto",
              p: 2,
              bgcolor: "action.hover"
            }}
          >
            <Stack spacing={1.25}>
              {(activeSession?.messages || []).map((m) => (
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
                      bgcolor: m.role === "user" ? "primary.main" : "background.paper",
                      color: m.role === "user" ? "primary.contrastText" : "text.primary",
                      border: m.role === "bot" ? "1px solid" : "none",
                      borderColor: "divider",
                      position: "relative"
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
                          <Button size="small" onClick={cancelEditBubble} disabled={bubbleSaving}>
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
                            sx={{ mt: 0.75, alignItems: "center", justifyContent: "space-between" }}
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
                                m.personaReason ? `persona: ${m.personaReason}` : ""
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
          </Box>
          <Box sx={{ p: 1.5, borderTop: "1px solid", borderColor: "divider" }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField
                fullWidth
                size="small"
                label="Ton message"
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
                  chatBusy ? <CircularProgress size={16} color="inherit" /> : <SendIcon />
                }
                onClick={() => void sendChat()}
                disabled={chatBusy || !chatInput.trim() || !activeSession}
              >
                Envoyer
              </Button>
            </Stack>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={openNewConversation} startIcon={<ChatIcon />}>
            Nlle conversation
          </Button>
          <Button onClick={closeChat}>Fermer</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editTag ? `Modifier ${editTag}` : "Nouvel intent"}</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
          {!editTag ? (
            <TextField
              label="Tag (ex. mon_intent)"
              size="small"
              value={form.tag}
              onChange={(e) => setForm((f) => ({ ...f, tag: e.target.value }))}
              helperText="Minuscules, chiffres, underscore. Unique."
            />
          ) : null}
          <TextField
            label="Priorite"
            size="small"
            type="number"
            value={form.priority}
            onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}
          />
          <TextField
            label="Action (optionnel)"
            size="small"
            value={form.action}
            onChange={(e) => setForm((f) => ({ ...f, action: e.target.value }))}
            helperText="ex. record_message, collect_coords, hangup_soft"
          />
          <TextField
            label="Patterns (un par ligne)"
            size="small"
            multiline
            minRows={4}
            value={form.patternsText}
            onChange={(e) => setForm((f) => ({ ...f, patternsText: e.target.value }))}
          />
          <TextField
            label="Reponses (une par ligne, 1ere = voix)"
            size="small"
            multiline
            minRows={3}
            value={form.responsesText}
            onChange={(e) => setForm((f) => ({ ...f, responsesText: e.target.value }))}
          />
          <FormControlLabel
            control={
              <Switch
                checked={form.enabled}
                onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
              />
            }
            label="Active"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Annuler</Button>
          <Button variant="contained" onClick={() => void saveIntent()} disabled={saving}>
            {saving ? "…" : "Enregistrer"}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(deleteTag)} onClose={() => setDeleteTag(null)}>
        <DialogTitle>Supprimer l'intent ?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Tu vas supprimer <strong>{deleteTag}</strong> (patterns, reponses, embeddings). Pas de
            retour en arriere.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTag(null)}>Annuler</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => void confirmDelete()}
            disabled={deleting}
          >
            {deleting ? "…" : "Supprimer"}
          </Button>
        </DialogActions>
      </Dialog>
    </AppLayout>
  );
}
