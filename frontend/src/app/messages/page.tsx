/**
 * Page Messages : messagerie vocale Material, audio lazy, cache soft.
 */

"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Collapse,
  FormControlLabel,
  IconButton,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Paper,
  Stack,
  Switch,
  Typography,
  Avatar
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import DeleteIcon from "@mui/icons-material/Delete";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import VoicemailIcon from "@mui/icons-material/Voicemail";
import MarkEmailUnreadIcon from "@mui/icons-material/MarkEmailUnread";
import { AppLayout } from "../../components/AppLayout";
import { VgPageHeader } from "../../components/mui/VgPageHeader";
import { VgSoftSyncBar } from "../../components/mui/VgSoftSyncBar";
import { VgTableSkeleton } from "../../components/mui/VgListSkeleton";
import { fetchDashboardStats, type DashboardStats } from "../../services/dashboardStatsApi";
import {
  deleteVoicemail,
  fetchVoicemails,
  markVoicemailRead,
  voicemailAudioUrl,
  type Voicemail
} from "../../services/voicemailsApi";
import {
  isAbortError,
  loadUiCache,
  saveUiCache,
  UI_CACHE_KEYS
} from "../../services/uiPersist";
import { formatApiDateTime, formatDurationMinSec } from "../../utils/dateTime";

const PAGE_SIZE = 20;

type StatsBox = {
  today: number;
  unread: number;
  total: number;
};

/**
 * Carte stats compacte Material.
 *
 * @param props label + valeur + accent.
 */
function StatChip({
  label,
  value,
  color
}: {
  label: string;
  value: number;
  color?: "default" | "warning" | "info" | "success";
}): React.ReactElement {
  return (
    <Paper
      variant="outlined"
      sx={{ px: 2, py: 1.25, minWidth: 120, flex: "1 1 120px" }}
    >
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        {label}
      </Typography>
      <Typography variant="h5" component="div" color={color === "warning" ? "warning.main" : undefined}>
        {value}
      </Typography>
    </Paper>
  );
}

/**
 * Ligne message : details + lecteur audio uniquement a l'ouverture.
 *
 * @param props message + handlers.
 */
function MessageRow({
  vm,
  expanded,
  onToggle,
  onDelete,
  onPlayed
}: {
  vm: Voicemail;
  expanded: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onPlayed: () => void;
}): React.ReactElement {
  const title = vm.phone_number || "Numero inconnu";
  const secondaryBits = [
    formatApiDateTime(vm.created_at),
    vm.duration != null ? formatDurationMinSec(vm.duration) : null,
    vm.call_id != null ? `appel #${vm.call_id}` : null
  ].filter(Boolean);

  return (
    <Paper
      variant="outlined"
      sx={{
        mb: 1,
        bgcolor: vm.is_read ? "background.paper" : "action.hover",
        borderColor: vm.is_read ? "divider" : "primary.main"
      }}
    >
      <ListItem
        alignItems="flex-start"
        secondaryAction={
          <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
            <IconButton
              edge="end"
              aria-label={expanded ? "Replier" : "Ecouter"}
              onClick={onToggle}
              size="small"
            >
              {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </IconButton>
            <IconButton
              edge="end"
              aria-label="Supprimer"
              onClick={onDelete}
              size="small"
              color="error"
            >
              <DeleteIcon />
            </IconButton>
          </Stack>
        }
        sx={{ pr: 12 }}
      >
        <ListItemAvatar>
          <Avatar
            sx={{
              bgcolor: vm.is_read ? "action.selected" : "primary.main",
              color: vm.is_read ? "text.secondary" : "primary.contrastText"
            }}
          >
            {vm.is_read ? <VoicemailIcon /> : <MarkEmailUnreadIcon />}
          </Avatar>
        </ListItemAvatar>
        <ListItemText
          primary={
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Typography
                variant="subtitle1"
                component="span"
                sx={{ fontWeight: vm.is_read ? 500 : 700 }}
              >
                {title}
              </Typography>
              {vm.caller_name ? (
                <Typography variant="body2" color="text.secondary" component="span">
                  {vm.caller_name}
                </Typography>
              ) : null}
              {!vm.is_read ? (
                <Chip size="small" color="primary" label="Nouveau" />
              ) : null}
            </Stack>
          }
          secondary={
            <Typography variant="caption" color="text.secondary" component="span">
              {secondaryBits.join(" · ")}
            </Typography>
          }
        />
      </ListItem>

      <Box sx={{ px: 2, pb: expanded ? 0 : 1.5 }}>
        {vm.transcription ? (
          <Typography
            variant="body2"
            sx={{ fontStyle: "italic", color: "text.secondary", mb: expanded ? 1 : 0 }}
          >
            « {vm.transcription} »
          </Typography>
        ) : (
          <Typography variant="body2" color="text.disabled" sx={{ mb: expanded ? 1 : 0 }}>
            Transcription en cours ou indisponible…
          </Typography>
        )}
      </Box>

      <Collapse in={expanded} unmountOnExit>
        <Box sx={{ px: 2, pb: 2 }}>
          {/* Lecteur monte seulement a l'ouverture : evite N telechargements qui figent la nav */}
          <audio
            controls
            preload="none"
            src={voicemailAudioUrl(vm.id)}
            style={{ width: "100%" }}
            onPlay={onPlayed}
          />
        </Box>
      </Collapse>
    </Paper>
  );
}

/**
 * Messagerie vocale apres le bip (Material).
 */
export default function MessagesPage(): React.ReactElement {
  const cached = loadUiCache<Voicemail[]>(UI_CACHE_KEYS.voicemails);
  const [items, setItems] = useState<Voicemail[]>(() => cached ?? []);
  const [loading, setLoading] = useState(() => !cached);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const abortRef = useRef<AbortController | null>(null);
  const [stats, setStats] = useState<StatsBox | null>(() => {
    const dash = loadUiCache<DashboardStats>(UI_CACHE_KEYS.dashboardStats);
    return dash
      ? {
          today: dash.voicemails_today ?? 0,
          unread: dash.voicemails_unread ?? 0,
          total: dash.voicemails_total ?? 0
        }
      : null;
  });

  const load = useCallback(async () => {
    const hasLocal = Boolean(loadUiCache(UI_CACHE_KEYS.voicemails));
    if (hasLocal) setSyncing(true);
    else setLoading(true);
    setError(null);

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    try {
      const [rows, dash] = await Promise.all([
        fetchVoicemails(
          {
            limit: 100,
            is_read: unreadOnly ? false : undefined
          },
          ac.signal
        ),
        fetchDashboardStats(ac.signal).catch(() => null)
      ]);
      if (ac.signal.aborted) return;
      setItems(rows);
      setVisibleCount(PAGE_SIZE);
      setExpandedId(null);
      if (!unreadOnly) saveUiCache(UI_CACHE_KEYS.voicemails, rows);
      if (dash) {
        saveUiCache(UI_CACHE_KEYS.dashboardStats, dash);
        setStats({
          today: dash.voicemails_today ?? 0,
          unread: dash.voicemails_unread ?? 0,
          total: dash.voicemails_total ?? 0
        });
      }
    } catch (e) {
      if (isAbortError(e) || ac.signal.aborted) return;
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      if (!ac.signal.aborted) {
        setLoading(false);
        setSyncing(false);
      }
    }
  }, [unreadOnly]);

  useEffect(() => {
    void load();
    return () => {
      abortRef.current?.abort();
    };
  }, [load]);

  const visibleItems = useMemo(
    () => items.slice(0, visibleCount),
    [items, visibleCount]
  );
  const hasMore = items.length > visibleCount;

  const onPlayed = useCallback(
    async (vm: Voicemail) => {
      if (vm.is_read) return;
      try {
        await markVoicemailRead(vm.id);
        setItems((prev) => {
          const next = prev.map((x) =>
            x.id === vm.id ? { ...x, is_read: true } : x
          );
          if (!unreadOnly) saveUiCache(UI_CACHE_KEYS.voicemails, next);
          return next;
        });
        setStats((s) => (s ? { ...s, unread: Math.max(0, s.unread - 1) } : s));
      } catch {
        /* lecture prioritaire */
      }
    },
    [unreadOnly]
  );

  const onDelete = useCallback(
    async (id: number) => {
      if (!window.confirm("Supprimer ce message ?")) return;
      try {
        const wasUnread = items.find((x) => x.id === id)?.is_read === false;
        await deleteVoicemail(id);
        setItems((prev) => {
          const next = prev.filter((x) => x.id !== id);
          if (!unreadOnly) saveUiCache(UI_CACHE_KEYS.voicemails, next);
          return next;
        });
        if (expandedId === id) setExpandedId(null);
        setStats((s) =>
          s
            ? {
                today: s.today,
                total: Math.max(0, s.total - 1),
                unread: wasUnread ? Math.max(0, s.unread - 1) : s.unread
              }
            : s
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "Suppression impossible");
      }
    },
    [items, unreadOnly, expandedId]
  );

  return (
    <AppLayout title="Messages" hidePageHeader>
      <VgPageHeader
        title="Messages"
        subtitle="Messages laisses apres le bip. Audio charge uniquement a l'ecoute."
        action={
          <Button
            size="small"
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={() => void load()}
            disabled={loading || syncing}
          >
            Rafraichir
          </Button>
        }
      />

      {syncing ? (
        <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
          <VgSoftSyncBar label="Synchro messages…" />
        </Box>
      ) : null}

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}

      {stats ? (
        <Stack
          direction="row"
          spacing={1.5}
          sx={{ mb: 2, flexWrap: "wrap", gap: 1.5 }}
        >
          <StatChip label="Non lus" value={stats.unread} color="warning" />
          <StatChip label="Aujourd'hui" value={stats.today} color="info" />
          <StatChip label="Total" value={stats.total} />
        </Stack>
      ) : null}

      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1}
        sx={{ mb: 2, alignItems: { sm: "center" }, justifyContent: "space-between" }}
      >
        <FormControlLabel
          control={
            <Switch
              checked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.checked)}
              size="small"
            />
          }
          label="Non lus seulement"
        />
        <Typography variant="caption" color="text.secondary">
          {items.length} message{items.length > 1 ? "s" : ""}
          {hasMore ? ` · ${visibleCount} affiches` : ""}
        </Typography>
      </Stack>

      {loading && items.length === 0 ? <VgTableSkeleton rows={5} /> : null}

      {!loading && items.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 3, textAlign: "center" }}>
          <VoicemailIcon color="disabled" sx={{ fontSize: 40, mb: 1 }} />
          <Typography color="text.secondary">
            Aucun message pour le moment. Appelle le repondeur pour en laisser un.
          </Typography>
        </Paper>
      ) : null}

      <List disablePadding>
        {visibleItems.map((vm) => (
          <MessageRow
            key={vm.id}
            vm={vm}
            expanded={expandedId === vm.id}
            onToggle={() =>
              setExpandedId((cur) => (cur === vm.id ? null : vm.id))
            }
            onDelete={() => void onDelete(vm.id)}
            onPlayed={() => void onPlayed(vm)}
          />
        ))}
      </List>

      {hasMore ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 2 }}>
          <Button
            variant="outlined"
            onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
          >
            Afficher plus ({items.length - visibleCount} restants)
          </Button>
        </Box>
      ) : null}
    </AppLayout>
  );
}
