import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  RefreshControl,
  Pressable,
  ActivityIndicator,
  Alert,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import type { VoicemailRow } from "../../src/db/schema";
import { getAppDb } from "../../src/db/getAppDb";
import { OfflineBanner } from "../../src/components/OfflineBanner";
import { getStoredCredentials } from "../../src/services/credentials";
import { isApiUnauthorized } from "../../src/services/api";
import { resolveConnectivityState } from "../../src/services/connectivity";
import { log } from "../../src/services/log";
import { setVoicemailPlayHandler } from "../../src/services/realtime";
import { syncFromServer } from "../../src/services/sync";
import { downloadVoicemailAudio, markVoicemailRead } from "../../src/services/voicemails";
import {
  stopVoicemailPlayback,
  subscribeVoicemailPlayer,
  toggleVoicemailPlayback,
  type VoicemailPlayerState,
} from "../../src/services/voicemailPlayer";
import { formatDuration, voicemailCallerLabel } from "../../src/utils/format";
import { colors } from "../../src/theme/colors";

const EMPTY_PLAYER: VoicemailPlayerState = {
  activeId: null,
  loadingId: null,
  playing: false,
  currentTime: 0,
  duration: 0,
};

/**
 * Liste messages vocaux avec sync, lecteur audio et transcription.
 */
export default function MessagesScreen() {
  const params = useLocalSearchParams<{ play?: string }>();
  const [rows, setRows] = useState<VoicemailRow[]>([]);
  const [connState, setConnState] = useState<"online" | "offline" | "syncing">("offline");
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [pullRefreshing, setPullRefreshing] = useState(false);
  const [player, setPlayer] = useState<VoicemailPlayerState>(EMPTY_PLAYER);
  const lastSyncRef = useRef<string | null>(null);
  const uriCacheRef = useRef<Map<number, string>>(new Map());

  const loadLocal = useCallback(async () => {
    const db = await getAppDb();
    const data = await db.getAllAsync<VoicemailRow>(
      "SELECT * FROM voicemails ORDER BY recorded_at DESC",
    );
    setRows(data);
    const sync = await db.getFirstAsync<{ last_sync_at: string | null }>(
      "SELECT last_sync_at FROM sync_state WHERE id = 1",
    );
    const at = sync?.last_sync_at ?? null;
    lastSyncRef.current = at;
    setLastSync(at);
  }, []);

  const playVoicemail = useCallback(async (item: VoicemailRow) => {
    try {
      let uri = uriCacheRef.current.get(item.id);
      if (!uri) {
        const { baseUrl, token } = await getStoredCredentials();
        if (!baseUrl || !token) {
          throw new Error("Pas de credentials");
        }
        uri = await downloadVoicemailAudio({ baseUrl, token }, item.id);
        uriCacheRef.current.set(item.id, uri);
      }
      await toggleVoicemailPlayback(item.id, uri);

      if (!item.is_read) {
        const { baseUrl, token } = await getStoredCredentials();
        if (baseUrl && token) {
          try {
            await markVoicemailRead({ baseUrl, token }, item.id);
            const db = await getAppDb();
            await db.runAsync("UPDATE voicemails SET is_read = 1 WHERE id = ?", [item.id]);
            setRows((prev) => prev.map((r) => (r.id === item.id ? { ...r, is_read: 1 } : r)));
          } catch (err) {
            log.warn("messages", "mark read failed", err);
          }
        }
      }
    } catch (err) {
      log.error("messages", "play failed", err);
      stopVoicemailPlayback();
      Alert.alert(
        "Lecture impossible",
        "Le message vocal n'a pas pu etre lu. Verifie ta connexion et reessaie.",
      );
    }
  }, []);

  const refresh = useCallback(
    async (reason: string) => {
      if (reason === "pull") setPullRefreshing(true);
      setConnState("syncing");
      let baseUrl = "";
      try {
        const creds = await getStoredCredentials();
        baseUrl = creds.baseUrl ?? "";
        if (baseUrl && creds.token) {
          const db = await getAppDb();
          await syncFromServer(db, { baseUrl, token: creds.token }, lastSyncRef.current);
        }
        await loadLocal();
        setConnState(await resolveConnectivityState(baseUrl));
      } catch (err) {
        if (!isApiUnauthorized(err)) {
          log.error("messages", "refresh failed", err);
        }
        setConnState("offline");
      } finally {
        setPullRefreshing(false);
      }
    },
    [loadLocal],
  );

  useEffect(() => {
    const unsub = subscribeVoicemailPlayer(setPlayer);
    return () => {
      unsub();
      stopVoicemailPlayback();
    };
  }, []);

  useEffect(() => {
    void (async () => {
      await loadLocal();
      await refresh("mount");
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- init once
  }, []);

  /** Re-sync tant qu un message recent n a pas encore sa transcription STT. */
  useEffect(() => {
    const cutoff = Date.now() - 2 * 60 * 60 * 1000;
    const needsTranscription = rows.some((row) => {
      if (row.transcription?.trim()) return false;
      const at = row.recorded_at ? Date.parse(row.recorded_at) : 0;
      return at > cutoff;
    });
    if (!needsTranscription) return;
    const timer = setInterval(() => {
      void refresh("stt-poll");
    }, 12000);
    return () => clearInterval(timer);
  }, [rows, refresh]);

  useEffect(() => {
    setVoicemailPlayHandler((id) => {
      const item = rows.find((r) => r.id === id);
      if (item) void playVoicemail(item);
    });
    return () => setVoicemailPlayHandler(null);
  }, [rows, playVoicemail]);

  useEffect(() => {
    const playParam = params.play;
    if (!playParam) return;
    const id = Number(playParam);
    if (!Number.isFinite(id)) return;
    const item = rows.find((r) => r.id === id);
    if (item) void playVoicemail(item);
  }, [params.play, rows, playVoicemail]);

  const unreadCount = rows.filter((r) => !r.is_read).length;

  return (
    <View style={styles.container}>
      <OfflineBanner
        state={connState}
        lastSyncLabel={
          lastSync
            ? `sync ${lastSync}${unreadCount > 0 ? ` · ${unreadCount} non lu(s)` : ""}`
            : unreadCount > 0
              ? `${unreadCount} non lu(s)`
              : undefined
        }
      />
      <FlatList
        data={rows}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl
            refreshing={pullRefreshing}
            onRefresh={() => void refresh("pull")}
            tintColor={colors.primary}
          />
        }
        ListEmptyComponent={
          <Text style={styles.empty}>Aucun message vocal. Tire pour synchroniser.</Text>
        }
        renderItem={({ item }) => {
          const caller = voicemailCallerLabel(item.caller_name, item.caller_number);
          const isActive = player.activeId === item.id;
          const isLoading = player.loadingId === item.id;
          const isPlaying = isActive && player.playing;
          const progressDuration = isActive
            ? Math.max(player.duration, item.duration, 1)
            : Math.max(item.duration, 1);
          const progress = isActive ? Math.min(1, player.currentTime / progressDuration) : 0;
          const elapsed = isActive ? player.currentTime : 0;

          return (
            <View style={styles.row}>
              <Pressable
                style={styles.playBtn}
                onPress={() => void playVoicemail(item)}
                accessibilityLabel={isPlaying ? "Pause" : "Ecouter"}
              >
                {isLoading ? (
                  <ActivityIndicator color={colors.primary} size="small" />
                ) : (
                  <MaterialCommunityIcons
                    name={isPlaying ? "pause-circle" : "play-circle"}
                    size={44}
                    color={colors.primary}
                  />
                )}
              </Pressable>
              <View style={styles.body}>
                <Text style={styles.phone}>
                  {caller.title}
                  {!item.is_read ? " · nouveau" : ""}
                </Text>
                {caller.subtitle ? <Text style={styles.subPhone}>{caller.subtitle}</Text> : null}
                {item.transcription ? (
                  <Text style={styles.transcription} numberOfLines={3}>
                    {item.transcription}
                  </Text>
                ) : item.recorded_at && Date.now() - Date.parse(item.recorded_at) < 2 * 60 * 60 * 1000 ? (
                  <Text style={styles.transcriptionPending}>Transcription en cours...</Text>
                ) : null}
                {isActive ? (
                  <View style={styles.player}>
                    <View style={styles.progressTrack}>
                      <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
                    </View>
                    <Text style={styles.progressTime}>
                      {formatDuration(Math.round(elapsed)) || "0:00"} /{" "}
                      {formatDuration(Math.round(progressDuration)) || formatDuration(item.duration) || "0:00"}
                    </Text>
                  </View>
                ) : null}
                <Text style={styles.meta}>
                  {item.is_read ? "Lu" : "Non lu"} · {item.duration}s
                  {item.recorded_at ? ` · ${item.recorded_at.slice(0, 16).replace("T", " ")}` : ""}
                </Text>
              </View>
            </View>
          );
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate },
  row: {
    flexDirection: "row",
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.slateLight,
    alignItems: "flex-start",
    gap: 12,
  },
  playBtn: { paddingTop: 2 },
  body: { flex: 1 },
  phone: { color: colors.text, fontSize: 16, fontWeight: "600" },
  subPhone: { color: colors.textMuted, marginTop: 2, fontSize: 13 },
  transcription: { color: colors.text, marginTop: 6, fontSize: 14, lineHeight: 20 },
  transcriptionPending: { color: colors.textMuted, marginTop: 6, fontSize: 13, fontStyle: "italic" },
  player: { marginTop: 10, gap: 4 },
  progressTrack: {
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.slateLight,
    overflow: "hidden",
  },
  progressFill: {
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.primary,
  },
  progressTime: { color: colors.textMuted, fontSize: 11 },
  meta: { color: colors.textMuted, marginTop: 4, fontSize: 12 },
  empty: { color: colors.textMuted, textAlign: "center", marginTop: 48, paddingHorizontal: 24 },
});
