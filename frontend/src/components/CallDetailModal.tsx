"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  IconButton,
  LinearProgress,
  Slider,
  Stack,
  Typography,
  useTheme
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import PauseIcon from "@mui/icons-material/Pause";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import SubtitlesIcon from "@mui/icons-material/Subtitles";
import type { CallWithOsint } from "../services/callsApi";
import { getCallRecordingUrl } from "../services/callsApi";
import { formatApiDateTime, formatDurationMinSec, parseApiUtcDate } from "../utils/dateTime";
import { getCallIncomingProfile, isCallWithoutMessage, CALL_NO_MESSAGE_LABEL } from "../utils/callProfile";
import { VgProfileChip } from "./mui/VgProfileChip";
import { KbIntentBars } from "./kb/KbIntentBars";
import { getWsBaseUrl } from "../services/httpClient";
import {
  buildTranscriptCues,
  cuesFromExtraData,
  findCueIndexAt,
  findWordIndexAt,
  type TranscriptCue
} from "../utils/transcriptCues";

const WORD_COLORS = ["#4ade80", "#38bdf8", "#fbbf24", "#c084fc", "#fb7185"];

type Props = {
  open: boolean;
  loading: boolean;
  call: CallWithOsint | null;
  onClose: () => void;
  onDelete: () => void;
  onRefreshOsint: () => void;
};

/**
 * Duree d'appel en secondes (champ API ou delta).
 *
 * @param call Appel API.
 * @returns Secondes, 0 si inconnue.
 */
function getCallDurationSec(call: CallWithOsint): number {
  let totalSec = Number(call.duration ?? 0);
  if (!Number.isFinite(totalSec) || totalSec <= 0) {
    if (call.answer_time && call.end_time) {
      const start = parseApiUtcDate(call.answer_time).getTime();
      const end = parseApiUtcDate(call.end_time).getTime();
      if (Number.isFinite(start) && Number.isFinite(end) && end > start) {
        totalSec = Math.floor((end - start) / 1000);
      }
    }
  }
  return Number.isFinite(totalSec) && totalSec > 0 ? totalSec : 0;
}

function formatClock(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0:00";
  const s = Math.floor(sec);
  const m = Math.floor(s / 60);
  return `${m}:${(s % 60).toString().padStart(2, "0")}`;
}

function statusChip(status: string): { label: string; color: "success" | "warning" | "error" | "info" | "default" } {
  const n = status.toLowerCase();
  if (n === "answered" || n === "completed") return { label: "Repondu", color: "success" };
  if (n === "missed") return { label: "Manque", color: "warning" };
  if (n === "blocked") return { label: "Bloque", color: "error" };
  if (n === "dialing") return { label: "Composition", color: "info" };
  return { label: status, color: "default" };
}

/**
 * Scene karaoke : 4-5 mots, couleurs et tailles, synchro avec l'audio.
 *
 * @param cues Groupes SRT.
 * @param cueIndex Groupe actif.
 * @param wordIndex Mot actif dans le groupe.
 * @param onSeekWord Seek audio au debut d'un mot.
 * @param onSeekCue Seek audio au debut d'un groupe.
 */
function KaraokeStage({
  cues,
  cueIndex,
  wordIndex,
  onSeekWord,
  onSeekCue
}: {
  cues: TranscriptCue[];
  cueIndex: number;
  wordIndex: number;
  onSeekWord: (start: number) => void;
  onSeekCue: (start: number) => void;
}): React.ReactElement {
  const cue = cueIndex >= 0 ? cues[cueIndex] : undefined;
  if (!cue) {
    return (
      <Typography color="text.secondary" sx={{ textAlign: "center", py: 5 }}>
        Pas encore de transcription.
      </Typography>
    );
  }

  const cueProgress =
    cue.end > cue.start ? Math.min(1, Math.max(0, (wordIndex + 0.5) / cue.words.length)) : 0;

  return (
    <Box
      sx={{
        minHeight: { xs: 188, sm: 228 },
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        px: { xs: 1.5, sm: 3 },
        py: 2
      }}
    >
      <Box
        key={cue.index}
        sx={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "flex-end",
          gap: { xs: 1, sm: 1.4 },
          maxWidth: 680,
          minHeight: { xs: 92, sm: 112 }
        }}
      >
        {cue.words.map((word, i) => {
          const active = i === wordIndex;
          const color = WORD_COLORS[i % WORD_COLORS.length];
          const lenBoost = Math.min(word.text.length, 14) * 0.07;
          const mid = Math.floor((cue.words.length - 1) / 2);
          const dist = Math.abs(i - mid);
          const archBoost = dist === 0 ? 0.32 : dist === 1 ? 0.08 : 0;
          const fontSize = `${(active ? 1.72 : 1.12) + lenBoost + archBoost}rem`;
          return (
            <Box
              key={`${cue.index}-${i}-${word.text}`}
              component="button"
              type="button"
              onClick={() => onSeekWord(word.start)}
              aria-current={active ? "true" : undefined}
              aria-label={`Aller a ${word.text}`}
              sx={{
                border: "none",
                cursor: "pointer",
                px: { xs: 1.1, sm: 1.4 },
                py: { xs: 0.45, sm: 0.6 },
                borderRadius: 999,
                bgcolor: active ? `${color}26` : "rgba(255,255,255,0.04)",
                boxShadow: active ? `0 10px 28px ${color}44` : "none",
                color,
                fontWeight: active ? 800 : 650,
                fontSize,
                lineHeight: 1.1,
                letterSpacing: active ? "0.012em" : 0,
                textShadow: active ? `0 0 22px ${color}aa` : "none",
                transform: active ? "translateY(-8px) scale(1.08)" : "translateY(0)",
                opacity: active ? 1 : 0.62,
                animation: `vgKaraokeIn 0.48s cubic-bezier(0.22, 1, 0.36, 1) ${i * 55}ms both`,
                "@keyframes vgKaraokeIn": {
                  from: { opacity: 0, transform: "translateY(22px) rotate(-4deg) scale(0.82)" },
                  to: {
                    opacity: active ? 1 : 0.62,
                    transform: active ? "translateY(-8px) scale(1.08)" : "translateY(0) scale(1)"
                  }
                },
                transition:
                  "transform 0.22s ease, opacity 0.22s ease, box-shadow 0.22s ease, background-color 0.22s ease",
                "&:hover": {
                  opacity: 1,
                  transform: "translateY(-4px) scale(1.05)",
                  bgcolor: `${color}22`
                }
              }}
            >
              {word.text}
            </Box>
          );
        })}
      </Box>
      <LinearProgress
        variant="determinate"
        value={cueProgress * 100}
        sx={{
          mt: 2.25,
          width: "min(280px, 70%)",
          height: 4,
          borderRadius: 99,
          bgcolor: "rgba(255,255,255,0.08)",
          "& .MuiLinearProgress-bar": { borderRadius: 99, bgcolor: WORD_COLORS[wordIndex % WORD_COLORS.length] }
        }}
      />
      <Stack direction="row" spacing={0.6} sx={{ mt: 1.75, flexWrap: "wrap", justifyContent: "center" }}>
        {cues.map((item, i) => (
          <Box
            key={item.index}
            component="button"
            type="button"
            onClick={() => onSeekCue(item.start)}
            aria-label={`Groupe ${i + 1}`}
            sx={{
              width: i === cueIndex ? 18 : 7,
              height: 7,
              border: "none",
              borderRadius: 99,
              p: 0,
              cursor: "pointer",
              bgcolor: i === cueIndex ? "primary.main" : "action.disabled",
              transition: "width 0.2s ease, background-color 0.2s ease"
            }}
          />
        ))}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ mt: 1, letterSpacing: "0.1em" }}>
        {cue.index + 1} / {cues.length}
      </Typography>
    </Box>
  );
}

/**
 * Modale detail d'appel : lecteur Material + sous-titres karaoke.
 */
export function CallDetailModal({
  open,
  loading,
  call,
  onClose,
  onDelete,
  onRefreshOsint
}: Props): React.ReactElement {
  const theme = useTheme();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const [fullTextOpen, setFullTextOpen] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [liveBelief, setLiveBelief] = useState<Array<{ tag: string; score: number }>>([]);
  const [liveCommit, setLiveCommit] = useState<string | null>(null);

  const recordingUrl = call?.audio_file ? getCallRecordingUrl(call.id) : null;
  const fallbackDuration = call ? getCallDurationSec(call) : 0;
  const duration = audioDuration > 0.4 ? audioDuration : fallbackDuration;

  const cues = useMemo(() => {
    if (!call || isCallWithoutMessage(call)) return [];
    const stored = cuesFromExtraData(call.extra_data ?? null);
    if (stored && stored.length > 0) return stored;
    return buildTranscriptCues(call.transcription || "", duration);
  }, [call, duration]);

  const noMessage = Boolean(call && isCallWithoutMessage(call));
  const showPlayer = Boolean(recordingUrl) && !noMessage;

  const cueIndex = findCueIndexAt(cues, currentTime);
  const wordIndex = cueIndex >= 0 && cues[cueIndex] ? findWordIndexAt(cues[cueIndex], currentTime) : 0;

  useEffect(() => {
    setPlaying(false);
    setCurrentTime(0);
    setAudioDuration(0);
    setFullTextOpen(false);
    setLiveTranscript("");
    setLiveBelief([]);
    setLiveCommit(null);
  }, [call?.id]);

  useEffect(() => {
    if (!open || !call?.id) return undefined;
    let ws: WebSocket | null = null;
    let cancelled = false;
    const callId = call.id;

    const connect = () => {
      if (cancelled) return;
      try {
        ws = new WebSocket(`${getWsBaseUrl()}/ws/events`);
      } catch {
        return;
      }
      ws.onmessage = (ev) => {
        let msg: { type?: string; data?: Record<string, unknown> };
        try {
          msg = JSON.parse(String(ev.data)) as { type?: string; data?: Record<string, unknown> };
        } catch {
          return;
        }
        const data = msg.data || {};
        const id = Number(data.call_id);
        if (!Number.isFinite(id) || id !== callId) return;
        const t = String(msg.type || "");
        if (t === "call.transcription.partial") {
          const text = String(data.text || "").trim();
          if (!text) return;
          // live:true = chunk en cours ; sinon tour confirme
          setLiveTranscript(text);
        }
        if (t === "call.intent.belief") {
          const top = Array.isArray(data.top) ? data.top : [];
          setLiveBelief(
            top
              .map((row) => {
                const r = row as { tag?: string; score?: number };
                return { tag: String(r.tag || ""), score: Number(r.score || 0) };
              })
              .filter((r) => r.tag)
          );
        }
        if (t === "call.intent.commit") {
          const tag = String(data.tag || "").trim();
          if (tag) setLiveCommit(tag);
          const text = String(data.text || "").trim();
          if (text) setLiveTranscript(text);
        }
      };
    };
    connect();
    return () => {
      cancelled = true;
      try {
        ws?.close();
      } catch {
        /* ignore */
      }
    };
  }, [open, call?.id]);

  const onTimeUpdate = useCallback(() => {
    const el = audioRef.current;
    if (!el) return;
    setCurrentTime(el.currentTime);
  }, []);

  const seekTo = useCallback((sec: number, playAfter: boolean = false) => {
    const t = Math.max(0, sec);
    const el = audioRef.current;
    if (el) {
      el.currentTime = t;
      setCurrentTime(el.currentTime);
      if (playAfter) {
        void el.play().then(() => setPlaying(true)).catch(() => undefined);
      }
      return;
    }
    setCurrentTime(t);
  }, []);

  const togglePlay = useCallback(() => {
    const el = audioRef.current;
    if (!el) return;
    if (el.paused) {
      void el.play().then(() => setPlaying(true)).catch(() => undefined);
    } else {
      el.pause();
      setPlaying(false);
    }
  }, []);

  useEffect(() => {
    if (!playing) return undefined;
    let raf = 0;
    const tick = () => {
      const el = audioRef.current;
      if (el) setCurrentTime(el.currentTime);
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [playing]);

  const st = call ? statusChip(call.status) : null;
  const profile = call ? getCallIncomingProfile(call) : null;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="md"
      aria-labelledby="vg-call-detail-title"
      slotProps={{
        paper: {
          sx: {
            overflow: "hidden",
            backgroundImage: "none",
            bgcolor: "background.paper"
          }
        }
      }}
    >
      {loading || !call ? (
        <DialogContent sx={{ py: 8, display: "flex", justifyContent: "center" }}>
          <CircularProgress size={36} />
        </DialogContent>
      ) : (
        <>
          <Box
            sx={{
              px: { xs: 2, sm: 3 },
              pt: 2,
              pb: 1.5,
              display: "flex",
              alignItems: "flex-start",
              gap: 1.5
            }}
          >
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography id="vg-call-detail-title" variant="h5" component="h2">
                Appel #{call.id}
              </Typography>
              <Typography variant="body1" sx={{ mt: 0.25 }} noWrap>
                {call.phone_number ?? "Numero inconnu"}
                {call.caller_name ? ` · ${call.caller_name}` : ""}
              </Typography>
              <Stack direction="row" spacing={0.75} useFlexGap sx={{ mt: 1, flexWrap: "wrap" }}>
                {st ? <Chip size="small" label={st.label} color={st.color} /> : null}
                {profile ? <VgProfileChip profile={profile} /> : null}
                {noMessage ? (
                  <Chip size="small" color="default" variant="outlined" label={CALL_NO_MESSAGE_LABEL} />
                ) : null}
                <Chip
                  size="small"
                  variant="outlined"
                  label={formatApiDateTime(call.call_time)}
                />
                {fallbackDuration > 0 && !noMessage ? (
                  <Chip size="small" variant="outlined" label={formatDurationMinSec(fallbackDuration)} />
                ) : null}
              </Stack>
            </Box>
            <IconButton aria-label="Fermer" onClick={onClose} edge="end">
              <CloseIcon />
            </IconButton>
          </Box>

          <DialogContent sx={{ px: { xs: 0, sm: 0 }, pt: 0, pb: 1 }}>
            {(liveTranscript || liveBelief.length > 0 || liveCommit) && (
              <Box sx={{ px: { xs: 2, sm: 3 }, pb: 2 }}>
                <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.75 }}>
                  Conversation en direct
                </Typography>
                {liveCommit ? (
                  <Chip size="small" color="success" label={`Intent: ${liveCommit}`} sx={{ mb: 1 }} />
                ) : null}
                {liveTranscript ? (
                  <Typography variant="body2" sx={{ mb: 1.25, whiteSpace: "pre-wrap" }}>
                    {liveTranscript}
                  </Typography>
                ) : null}
                <Stack spacing={0.75}>
                  <KbIntentBars
                    preds={liveBelief}
                    winner={liveCommit}
                    animKey={`${liveTranscript || ""}-${liveBelief.map((r) => `${r.tag}:${r.score.toFixed(2)}`).join("|")}`}
                  />
                </Stack>
              </Box>
            )}
            {noMessage ? (
              <Box
                sx={{
                  mx: { xs: 2, sm: 3 },
                  borderRadius: 3,
                  border: "1px solid",
                  borderColor: "divider",
                  px: 2.5,
                  py: 3,
                  textAlign: "center",
                  bgcolor:
                    theme.palette.mode === "dark" ? "rgba(15,20,28,0.72)" : "rgba(15,23,42,0.04)"
                }}
              >
                <Chip size="small" label={CALL_NO_MESSAGE_LABEL} sx={{ mb: 1.25 }} />
                <Typography variant="body1" color="text.secondary">
                  Aucun message vocal laisse sur le repondeur.
                </Typography>
                <Typography variant="caption" color="text.disabled" sx={{ mt: 0.75, display: "block" }}>
                  Pas d&apos;audio ni de transcription a afficher.
                </Typography>
              </Box>
            ) : (
              <Box
                sx={{
                  mx: { xs: 2, sm: 3 },
                  borderRadius: 3,
                  bgcolor: theme.palette.mode === "dark" ? "rgba(15,20,28,0.72)" : "rgba(15,23,42,0.04)",
                  border: "1px solid",
                  borderColor: "divider"
                }}
              >
                {recordingUrl ? (
                  <audio
                    ref={audioRef}
                    src={recordingUrl}
                    preload="metadata"
                    onTimeUpdate={onTimeUpdate}
                    onLoadedMetadata={(e) => {
                      const d = e.currentTarget.duration;
                      if (Number.isFinite(d) && d > 0) setAudioDuration(d);
                    }}
                    onPlay={() => setPlaying(true)}
                    onPause={() => setPlaying(false)}
                    onEnded={() => setPlaying(false)}
                    style={{ display: "none" }}
                  />
                ) : null}

                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 1,
                    px: 1.5,
                    pt: 1.25,
                    color: "text.secondary"
                  }}
                >
                  <SubtitlesIcon fontSize="small" />
                  <Typography variant="overline" sx={{ letterSpacing: "0.12em" }}>
                    Sous-titres
                  </Typography>
                </Box>
                <KaraokeStage
                  cues={cues}
                  cueIndex={cueIndex}
                  wordIndex={wordIndex}
                  onSeekWord={(start) => seekTo(start, true)}
                  onSeekCue={(start) => seekTo(start, true)}
                />
                <Box sx={{ px: 2, pb: 2, display: "flex", alignItems: "center", gap: 1.5 }}>
                  <IconButton
                    color="primary"
                    onClick={togglePlay}
                    disabled={!showPlayer}
                    aria-label={playing ? "Pause" : "Lecture"}
                    sx={{
                      bgcolor: "primary.main",
                      color: "primary.contrastText",
                      width: 48,
                      height: 48,
                      "&:hover": { bgcolor: "primary.dark" },
                      "&.Mui-disabled": { bgcolor: "action.disabledBackground" }
                    }}
                  >
                    {playing ? <PauseIcon /> : <PlayArrowIcon />}
                  </IconButton>
                  <Typography
                    variant="caption"
                    sx={{ fontVariantNumeric: "tabular-nums", minWidth: 36, color: "text.secondary" }}
                  >
                    {formatClock(currentTime)}
                  </Typography>
                  <Slider
                    size="small"
                    disabled={!showPlayer || duration <= 0}
                    min={0}
                    max={Math.max(duration, 0.01)}
                    step={0.05}
                    value={Math.min(currentTime, duration || 0)}
                    onChange={(_e, v) => seekTo(Array.isArray(v) ? v[0] : v, false)}
                    aria-label="Position lecture"
                    sx={{ flex: 1 }}
                  />
                  <Typography
                    variant="caption"
                    sx={{ fontVariantNumeric: "tabular-nums", minWidth: 36, color: "text.secondary" }}
                  >
                    {formatClock(duration)}
                  </Typography>
                </Box>
                {!recordingUrl ? (
                  <Typography variant="body2" color="text.secondary" sx={{ px: 2, pb: 2 }}>
                    Aucun fichier audio pour cet appel.
                  </Typography>
                ) : null}
              </Box>
            )}

            {!noMessage && call.transcription?.trim() ? (
              <Box sx={{ mx: { xs: 2, sm: 3 }, mt: 1.5 }}>
                <Button
                  size="small"
                  color="inherit"
                  onClick={() => setFullTextOpen((v) => !v)}
                  endIcon={fullTextOpen ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  sx={{ color: "text.secondary" }}
                >
                  Texte complet
                </Button>
                <Collapse in={fullTextOpen}>
                  <Typography
                    variant="body2"
                    sx={{
                      mt: 0.5,
                      p: 1.5,
                      borderRadius: 2,
                      bgcolor: "action.hover",
                      whiteSpace: "pre-wrap",
                      color: "text.secondary",
                      lineHeight: 1.55
                    }}
                  >
                    {call.transcription}
                  </Typography>
                </Collapse>
              </Box>
            ) : null}

            <Box sx={{ mx: { xs: 2, sm: 3 }, mt: 2 }}>
              <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: "0.12em" }}>
                OSINT
              </Typography>
              {call.osint ? (
                <Stack direction="row" spacing={0.75} useFlexGap sx={{ mt: 0.75, flexWrap: "wrap" }}>
                  {call.osint.company_name || call.osint.name ? (
                    <Chip
                      size="small"
                      color="primary"
                      variant="outlined"
                      label={call.osint.company_name || call.osint.name}
                    />
                  ) : null}
                  <Chip size="small" label={`${call.osint.recommendation} / ${call.osint.reputation}`} />
                  {call.osint.operator ? <Chip size="small" variant="outlined" label={call.osint.operator} /> : null}
                  {[call.osint.city, call.osint.region].filter(Boolean).length > 0 ? (
                    <Chip
                      size="small"
                      variant="outlined"
                      label={[call.osint.city, call.osint.region].filter(Boolean).join(", ")}
                    />
                  ) : null}
                  {call.osint.is_spam ? <Chip size="small" color="warning" label="Spam" /> : null}
                  {call.osint.is_scam ? <Chip size="small" color="error" label="Arnaque" /> : null}
                  {call.osint.is_telemarketer ? (
                    <Chip size="small" color="warning" label="Demarchage" />
                  ) : null}
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  Pas de profil OSINT en base.
                </Typography>
              )}
              <Button size="small" variant="outlined" onClick={onRefreshOsint} sx={{ mt: 1 }}>
                Rafraichir OSINT
              </Button>
            </Box>
          </DialogContent>

          <DialogActions sx={{ px: 3, py: 2 }}>
            <Button color="error" variant="contained" onClick={onDelete}>
              Supprimer
            </Button>
            <Box sx={{ flex: 1 }} />
            <Button onClick={onClose} variant="text">
              Fermer
            </Button>
          </DialogActions>
        </>
      )}
    </Dialog>
  );
}
