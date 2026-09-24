import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Modal,
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  ScrollView,
} from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import type { CallRow } from "../db/schema";
import { parseCallOsint } from "../db/schema";
import { KaraokeStage } from "./KaraokeStage";
import { CallOsintPanel } from "./CallOsintPanel";
import { CallSoundtrackBar } from "./CallSoundtrackBar";
import { CallStatusBadge } from "./CallStatusBadge";
import { getStoredCredentials } from "../services/credentials";
import {
  downloadCallRecording,
  fetchCallDetail,
  fetchCallDetailSoft,
  type CallDetail,
} from "../services/calls";
import {
  ensureCallPlaying,
  seekCallPlayback,
  skipCallPlayback,
  stopCallPlayback,
  subscribeCallPlayer,
  toggleCallPlayback,
  type CallPlayerState,
} from "../services/callPlayer";
import { stopVoicemailPlayback } from "../services/voicemailPlayer";
import { log } from "../services/log";
import { formatDetailDateTime, formatDurationMinSec, formatPhone } from "../utils/format";
import { resolveCallCues } from "../utils/resolveCallCues";
import type { TranscriptCue } from "../utils/transcriptCues";
import { colors } from "../theme/colors";
import { icons } from "../theme/icons";
import { getAppDb } from "../db/getAppDb";

const EMPTY_PLAYER: CallPlayerState = {
  activeId: null,
  loadingId: null,
  playing: false,
  currentTime: 0,
  duration: 0,
};

type Props = {
  call: CallRow | null;
  visible: boolean;
  onClose: () => void;
  onRecall: (phone: string) => void;
  /** Notifie le parent apres refresh OSINT (pour recharger la liste). */
  onOsintUpdated?: () => void;
};

/**
 * Modal detail appel alignee web :
 * header chips, cadre Sous-titres (karaoke + lecteur), texte complet, OSINT.
 */
export function CallDetailModal({ call, visible, onClose, onRecall, onOsintUpdated }: Props) {
  const [detail, setDetail] = useState<CallDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailHint, setDetailHint] = useState<string | null>(null);
  const [audioUri, setAudioUri] = useState<string | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [player, setPlayer] = useState<CallPlayerState>(EMPTY_PLAYER);
  const [playError, setPlayError] = useState<string | null>(null);
  const [fullTextOpen, setFullTextOpen] = useState(false);
  const [osintRefreshing, setOsintRefreshing] = useState(false);
  const uriCacheRef = useRef<Map<number, string>>(new Map());

  useEffect(() => {
    return subscribeCallPlayer(setPlayer);
  }, []);

  useEffect(() => {
    if (!visible || !call) {
      setDetail(null);
      setAudioUri(null);
      setAudioError(null);
      setDetailHint(null);
      setPlayError(null);
      setFullTextOpen(false);
      return;
    }

    let cancelled = false;
    setLoadingDetail(true);
    setAudioError(null);
    setDetailHint(null);
    setPlayError(null);
    setDetail(null);
    setFullTextOpen(false);
    stopVoicemailPlayback();
    stopCallPlayback();

    void (async () => {
      try {
        const { baseUrl, token } = await getStoredCredentials();
        if (!baseUrl || !token) {
          if (!cancelled) {
            setDetailHint("Pas de credentials (reconnecte l app).");
            setAudioError("Enregistrement indisponible sans connexion.");
          }
          return;
        }
        const config = { baseUrl, token };

        const { detail: remote, error: softErr } = await fetchCallDetailSoft(config, call.id);
        if (cancelled) return;
        if (remote) {
          setDetail(remote);
          setDetailHint(null);
        } else if (softErr) {
          setDetailHint(softErr);
        }

        try {
          let uri = uriCacheRef.current.get(call.id);
          if (!uri) {
            uri = await downloadCallRecording(config, call.id);
            uriCacheRef.current.set(call.id, uri);
          }
          if (!cancelled) setAudioUri(uri);
        } catch (err) {
          log.warn("callDetail", "audio unavailable", err);
          if (!cancelled) {
            const msg =
              err instanceof Error && err.message.includes("(404)")
                ? "Aucun fichier audio pour cet appel."
                : "Enregistrement indisponible.";
            setAudioError(msg);
          }
        }
      } catch (err) {
        log.error("callDetail", "load failed", err);
        if (!cancelled) {
          setDetailHint(err instanceof Error ? err.message : "Chargement impossible.");
        }
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [visible, call?.id]);

  const handleClose = useCallback(() => {
    stopCallPlayback();
    onClose();
  }, [onClose]);

  const cues: TranscriptCue[] = useMemo(() => resolveCallCues(call, detail), [detail, call]);

  const phone = detail?.phone_number ?? call?.phone_number ?? "";
  const phoneFmt = phone ? formatPhone(phone) : "";
  const name = (detail?.caller_name ?? call?.caller_name ?? "").trim();
  const isOutgoingLabel = name.toLowerCase() === "sortant";
  const callId = call?.id ?? detail?.id;
  const osint = detail?.osint
    ? parseCallOsint(JSON.stringify(detail.osint))
    : parseCallOsint(call?.osint_json);
  const fullTranscript = (detail?.transcription ?? call?.transcription ?? "").trim() || null;
  const noMessage = Boolean(detail?.no_message || call?.no_message);
  const durationSec = Number(detail?.duration ?? call?.duration ?? 0);
  const status = detail?.status ?? call?.status;
  const callTime = detail?.call_time ?? call?.call_time ?? null;

  const isActive = call != null && player.activeId === call.id;
  const isLoading = call != null && player.loadingId === call.id;
  const isPlaying = isActive && player.playing;
  const playerDur = Number.isFinite(player.duration) ? player.duration : 0;
  const callDur = Number.isFinite(durationSec) ? durationSec : 0;
  const totalDur = Math.max(isActive ? playerDur : 0, callDur, 1);
  const currentTime = isActive && Number.isFinite(player.currentTime) ? player.currentTime : 0;
  const progress = totalDur > 0 ? Math.min(1, Math.max(0, currentTime / totalDur)) : 0;

  const seekToRatio = useCallback(
    (ratio: number) => {
      if (!call || !audioUri || !Number.isFinite(totalDur) || totalDur <= 0) return;
      if (!Number.isFinite(ratio)) return;
      const target = Math.min(1, Math.max(0, ratio)) * totalDur;
      if (!Number.isFinite(target)) return;
      void (async () => {
        await ensureCallPlaying(call.id, audioUri);
        seekCallPlayback(target);
      })();
    },
    [totalDur, audioUri, call],
  );

  const onTogglePlay = useCallback(async () => {
    if (!call || !audioUri) return;
    try {
      setPlayError(null);
      await toggleCallPlayback(call.id, audioUri);
    } catch (err) {
      log.error("callDetail", "play failed", err);
      setPlayError("Lecture impossible. Verifie la connexion et reessaie.");
    }
  }, [call, audioUri]);

  const onSkip = useCallback(
    (delta: number) => {
      if (!call || !audioUri) return;
      void (async () => {
        await ensureCallPlaying(call.id, audioUri);
        skipCallPlayback(delta);
      })();
    },
    [audioUri, call],
  );

  const onSeekWord = useCallback(
    (startSec: number) => {
      if (!call || !audioUri) return;
      if (!Number.isFinite(startSec)) return;
      void (async () => {
        await ensureCallPlaying(call.id, audioUri);
        seekCallPlayback(startSec);
      })();
    },
    [audioUri, call],
  );

  const onRefreshOsint = useCallback(async () => {
    if (!call) return;
    setOsintRefreshing(true);
    try {
      const { baseUrl, token } = await getStoredCredentials();
      if (!baseUrl || !token) {
        setDetailHint("Pas de credentials pour rafraichir OSINT.");
        return;
      }
      const remote = await fetchCallDetail({ baseUrl, token }, call.id);
      setDetail(remote);
      if (remote.osint) {
        try {
          const db = await getAppDb();
          await db.runAsync("UPDATE calls SET osint_json = ? WHERE id = ?", [
            JSON.stringify(remote.osint),
            call.id,
          ]);
          onOsintUpdated?.();
        } catch (err) {
          log.warn("callDetail", "osint cache update failed", err);
        }
      }
    } catch (err) {
      log.warn("callDetail", "osint refresh failed", err);
      setDetailHint("Impossible de rafraichir OSINT.");
    } finally {
      setOsintRefreshing(false);
    }
  }, [call, onOsintUpdated]);

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={handleClose}>
      <View style={styles.container}>
        <View style={styles.header}>
          <View style={styles.headerMain}>
            <Text style={styles.headerTitle}>
              {callId != null ? `Appel #${callId}` : "Appel"}
            </Text>
            <Text style={styles.headerSub} numberOfLines={1}>
              {phoneFmt || "Numero inconnu"}
              {!isOutgoingLabel && name ? ` · ${name}` : ""}
            </Text>
            <View style={styles.chipRow}>
              <CallStatusBadge status={status} />
              {noMessage ? (
                <View style={styles.metaChip}>
                  <Text style={styles.metaChipText}>Filtre</Text>
                </View>
              ) : null}
              {callTime ? (
                <View style={styles.metaChip}>
                  <Text style={styles.metaChipText}>{formatDetailDateTime(callTime)}</Text>
                </View>
              ) : null}
              {durationSec > 0 && !noMessage ? (
                <View style={styles.metaChip}>
                  <Text style={styles.metaChipText}>{formatDurationMinSec(durationSec)}</Text>
                </View>
              ) : null}
            </View>
            {detailHint ? <Text style={styles.hint}>{detailHint}</Text> : null}
          </View>
          <View style={styles.headerActions}>
            {phoneFmt ? (
              <Pressable
                onPress={() => {
                  handleClose();
                  onRecall(phone);
                }}
                hitSlop={10}
                accessibilityLabel="Rappeler"
              >
                <MaterialCommunityIcons name={icons.recall} size={22} color={colors.primary} />
              </Pressable>
            ) : null}
            <Pressable onPress={handleClose} hitSlop={10} accessibilityLabel="Fermer">
              <MaterialCommunityIcons name={icons.close} size={24} color={colors.text} />
            </Pressable>
          </View>
        </View>

        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          {noMessage ? (
            <View style={styles.frame}>
              <View style={styles.noMsgChip}>
                <Text style={styles.noMsgChipText}>Filtre</Text>
              </View>
              <Text style={styles.noMsgTitle}>Aucun message vocal laisse sur le repondeur.</Text>
              <Text style={styles.noMsgSub}>Pas d'audio ni de transcription a afficher.</Text>
            </View>
          ) : (
            <View style={styles.frame}>
              <View style={styles.frameHeader}>
                <MaterialCommunityIcons name="subtitles-outline" size={16} color={colors.textMuted} />
                <Text style={styles.frameTitle}>Sous-titres</Text>
              </View>

              {loadingDetail && !cues.length && !fullTranscript ? (
                <ActivityIndicator color={colors.primary} style={{ marginVertical: 32 }} />
              ) : (
                <KaraokeStage
                  cues={cues}
                  currentTime={currentTime}
                  onSeekWord={onSeekWord}
                  onSeekCue={onSeekWord}
                />
              )}

              <CallSoundtrackBar
                callId={call?.id ?? 0}
                currentTime={currentTime}
                duration={totalDur}
                playing={isPlaying}
                loading={(loadingDetail && !audioUri && !audioError) || isLoading}
                disabled={!audioUri}
                cueMarks={cues.map((c) => c.start)}
                onTogglePlay={() => void onTogglePlay()}
                onSeekRatio={seekToRatio}
                onSkip={onSkip}
                error={playError || (audioError && !audioUri ? audioError : null)}
              />
            </View>
          )}

          {!noMessage && fullTranscript ? (
            <View style={styles.fullTextBlock}>
              <Pressable
                style={styles.fullTextToggle}
                onPress={() => setFullTextOpen((v) => !v)}
                accessibilityRole="button"
              >
                <Text style={styles.fullTextToggleLabel}>Texte complet</Text>
                <MaterialCommunityIcons
                  name={fullTextOpen ? "chevron-up" : "chevron-down"}
                  size={20}
                  color={colors.textMuted}
                />
              </Pressable>
              {fullTextOpen ? (
                <View style={styles.fullTextBody}>
                  <Text style={styles.fullText}>{fullTranscript}</Text>
                </View>
              ) : null}
            </View>
          ) : null}

          <CallOsintPanel
            osint={osint}
            phoneLabel={phoneFmt || undefined}
            onRefresh={() => void onRefreshOsint()}
            refreshing={osintRefreshing}
          />
        </ScrollView>

        <View style={styles.footer}>
          <View style={{ flex: 1 }} />
          <Pressable onPress={handleClose} accessibilityRole="button">
            <Text style={styles.footerClose}>Fermer</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate },
  header: {
    flexDirection: "row",
    alignItems: "flex-start",
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 12,
    gap: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "rgba(148,163,184,0.2)",
  },
  headerMain: { flex: 1, gap: 4, minWidth: 0 },
  headerTitle: { color: colors.text, fontSize: 22, fontWeight: "700" },
  headerSub: { color: colors.neutral200, fontSize: 15 },
  headerActions: { flexDirection: "row", alignItems: "center", gap: 14, paddingTop: 4 },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 },
  metaChip: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "rgba(148,163,184,0.35)",
  },
  metaChipText: { color: colors.textMuted, fontSize: 12, fontWeight: "600" },
  hint: { color: "#fbbf24", fontSize: 12, marginTop: 4 },
  content: { padding: 16, gap: 16, paddingBottom: 24 },
  frame: {
    backgroundColor: "rgba(15,20,28,0.72)",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "rgba(148,163,184,0.18)",
    overflow: "hidden",
    paddingBottom: 12,
  },
  frameHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 14,
    paddingTop: 12,
  },
  frameTitle: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 1.2,
  },
  fullTextBlock: { gap: 6 },
  fullTextToggle: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    alignSelf: "flex-start",
  },
  fullTextToggleLabel: { color: colors.textMuted, fontSize: 14, fontWeight: "600" },
  fullTextBody: {
    backgroundColor: "rgba(148,163,184,0.1)",
    borderRadius: 12,
    padding: 12,
  },
  fullText: { color: colors.textMuted, fontSize: 14, lineHeight: 22 },
  noMsgChip: {
    alignSelf: "center",
    marginTop: 20,
    marginBottom: 10,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
    backgroundColor: "rgba(148,163,184,0.15)",
  },
  noMsgChipText: { color: colors.textMuted, fontSize: 12, fontWeight: "600" },
  noMsgTitle: {
    color: colors.neutral200,
    fontSize: 15,
    textAlign: "center",
    paddingHorizontal: 20,
  },
  noMsgSub: {
    color: colors.textMuted,
    fontSize: 12,
    textAlign: "center",
    marginTop: 8,
    marginBottom: 20,
    paddingHorizontal: 20,
  },
  footer: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "rgba(148,163,184,0.2)",
  },
  footerClose: { color: colors.primary, fontSize: 16, fontWeight: "700" },
});
