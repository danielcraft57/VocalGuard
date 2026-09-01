import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  RefreshControl,
  Pressable,
  ActivityIndicator,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import type { VoicemailRow } from "../../src/db/schema";
import { getAppDb } from "../../src/db/getAppDb";
import { OfflineBanner } from "../../src/components/OfflineBanner";
import { getStoredCredentials } from "../../src/services/credentials";
import { resolveConnectivityState } from "../../src/services/connectivity";
import { log } from "../../src/services/log";
import { setVoicemailPlayHandler } from "../../src/services/realtime";
import { syncFromServer } from "../../src/services/sync";
import { markVoicemailRead, voicemailAudioUrl } from "../../src/services/voicemails";
import { colors } from "../../src/theme/colors";

/**
 * Liste messages vocaux avec sync, lecture audio et transcription.
 */
export default function MessagesScreen() {
  const params = useLocalSearchParams<{ play?: string }>();
  const [rows, setRows] = useState<VoicemailRow[]>([]);
  const [connState, setConnState] = useState<"online" | "offline" | "syncing">("offline");
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [pullRefreshing, setPullRefreshing] = useState(false);
  const [playingId, setPlayingId] = useState<number | null>(null);
  const [loadingId, setLoadingId] = useState<number | null>(null);
  const lastSyncRef = useRef<string | null>(null);
  const soundRef = useRef<{ unloadAsync: () => Promise<void> } | null>(null);

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

  const stopPlayback = useCallback(async () => {
    if (soundRef.current) {
      try {
        await soundRef.current.unloadAsync();
      } catch {
        /* ignore */
      }
      soundRef.current = null;
    }
    setPlayingId(null);
  }, []);

  const playVoicemail = useCallback(
    async (item: VoicemailRow) => {
      if (playingId === item.id) {
        await stopPlayback();
        return;
      }
      await stopPlayback();
      setLoadingId(item.id);
      try {
        const { baseUrl, token } = await getStoredCredentials();
        if (!baseUrl || !token) {
          throw new Error("Pas de credentials");
        }
        const config = { baseUrl, token };
        const uri = voicemailAudioUrl(config, item.id);

        const { Audio } = await import("expo-av");
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: false,
          playsInSilentModeIOS: true,
          staysActiveInBackground: false,
        });

        const { sound } = await Audio.Sound.createAsync(
          { uri, headers: { Authorization: `Bearer ${token}` } },
          { shouldPlay: true },
        );
        soundRef.current = sound;
        setPlayingId(item.id);
        setLoadingId(null);

        sound.setOnPlaybackStatusUpdate((status) => {
          if (!status.isLoaded) return;
          if (status.didJustFinish) {
            void stopPlayback();
          }
        });

        if (!item.is_read) {
          try {
            await markVoicemailRead(config, item.id);
            const db = await getAppDb();
            await db.runAsync("UPDATE voicemails SET is_read = 1 WHERE id = ?", [item.id]);
            setRows((prev) => prev.map((r) => (r.id === item.id ? { ...r, is_read: 1 } : r)));
          } catch (err) {
            log.warn("messages", "mark read failed", err);
          }
        }
      } catch (err) {
        log.error("messages", "play failed", err);
        setLoadingId(null);
        await stopPlayback();
      }
    },
    [playingId, stopPlayback],
  );

  const refresh = useCallback(
    async (reason: string) => {
      if (reason === "pull") setPullRefreshing(true);
      setConnState("syncing");
      try {
        const { baseUrl, token } = await getStoredCredentials();
        if (baseUrl && token) {
          const db = await getAppDb();
          await syncFromServer(db, { baseUrl, token }, lastSyncRef.current);
        }
        await loadLocal();
        setConnState(await resolveConnectivityState(baseUrl ?? ""));
      } catch (err) {
        log.error("messages", "refresh failed", err);
        setConnState("offline");
      } finally {
        setPullRefreshing(false);
      }
    },
    [loadLocal],
  );

  useEffect(() => {
    void (async () => {
      await loadLocal();
      await refresh("mount");
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- init once
  }, []);

  useEffect(() => {
    setVoicemailPlayHandler((id) => {
      const item = rows.find((r) => r.id === id);
      if (item) void playVoicemail(item);
    });
    return () => {
      setVoicemailPlayHandler(null);
      void stopPlayback();
    };
  }, [rows, playVoicemail, stopPlayback]);

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
          const isPlaying = playingId === item.id;
          const isLoading = loadingId === item.id;
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
                    size={40}
                    color={colors.primary}
                  />
                )}
              </Pressable>
              <View style={styles.body}>
                <Text style={styles.phone}>
                  {item.caller_name ?? item.caller_number}
                  {!item.is_read ? " · nouveau" : ""}
                </Text>
                {item.caller_name ? (
                  <Text style={styles.subPhone}>{item.caller_number}</Text>
                ) : null}
                {item.transcription ? (
                  <Text style={styles.transcription} numberOfLines={3}>
                    {item.transcription}
                  </Text>
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
  playBtn: { paddingTop: 4 },
  body: { flex: 1 },
  phone: { color: colors.text, fontSize: 16, fontWeight: "600" },
  subPhone: { color: colors.textMuted, marginTop: 2, fontSize: 13 },
  transcription: { color: colors.text, marginTop: 6, fontSize: 14, lineHeight: 20 },
  meta: { color: colors.textMuted, marginTop: 4, fontSize: 12 },
  empty: { color: colors.textMuted, textAlign: "center", marginTop: 48, paddingHorizontal: 24 },
});
