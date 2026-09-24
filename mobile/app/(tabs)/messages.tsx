import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  RefreshControl,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import type { VoicemailRow } from "../../src/db/schema";
import { getAppDb } from "../../src/db/getAppDb";
import { OfflineBanner } from "../../src/components/OfflineBanner";
import { VoicemailListItem } from "../../src/components/VoicemailListItem";
import { getStoredCredentials } from "../../src/services/credentials";
import { isApiUnauthorized } from "../../src/services/api";
import { resolveConnectivityState } from "../../src/services/connectivity";
import { log } from "../../src/services/log";
import { setVoicemailPlayHandler } from "../../src/services/realtime";
import { syncFromServer } from "../../src/services/sync";
import { downloadVoicemailAudio, markVoicemailRead } from "../../src/services/voicemails";
import { stopCallPlayback } from "../../src/services/callPlayer";
import {
  ensureVoicemailPlaying,
  seekVoicemailPlayback,
  skipVoicemailPlayback,
  stopVoicemailPlayback,
  subscribeVoicemailPlayer,
  toggleVoicemailPlayback,
  type VoicemailPlayerState,
} from "../../src/services/voicemailPlayer";
import { colors } from "../../src/theme/colors";

const EMPTY_PLAYER: VoicemailPlayerState = {
  activeId: null,
  loadingId: null,
  playing: false,
  currentTime: 0,
  duration: 0,
};

/**
 * Liste messages vocaux : bande sonore interactive par ligne,
 * une seule piste a la fois (coupe appels + autre message).
 */
export default function MessagesScreen() {
  const params = useLocalSearchParams<{ play?: string }>();
  const [rows, setRows] = useState<VoicemailRow[]>([]);
  const [connState, setConnState] = useState<"online" | "offline" | "syncing">("offline");
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [pullRefreshing, setPullRefreshing] = useState(false);
  const [player, setPlayer] = useState<VoicemailPlayerState>(EMPTY_PLAYER);
  const [playErrorById, setPlayErrorById] = useState<Record<number, string>>({});
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

  const resolveUri = useCallback(async (item: VoicemailRow): Promise<string> => {
    let uri = uriCacheRef.current.get(item.id);
    if (uri) return uri;
    const { baseUrl, token } = await getStoredCredentials();
    if (!baseUrl || !token) {
      throw new Error("Pas de credentials");
    }
    uri = await downloadVoicemailAudio({ baseUrl, token }, item.id);
    uriCacheRef.current.set(item.id, uri);
    return uri;
  }, []);

  const markReadIfNeeded = useCallback(async (item: VoicemailRow) => {
    if (item.is_read) return;
    const { baseUrl, token } = await getStoredCredentials();
    if (!baseUrl || !token) return;
    try {
      await markVoicemailRead({ baseUrl, token }, item.id);
      const db = await getAppDb();
      await db.runAsync("UPDATE voicemails SET is_read = 1 WHERE id = ?", [item.id]);
      setRows((prev) => prev.map((r) => (r.id === item.id ? { ...r, is_read: 1 } : r)));
    } catch (err) {
      log.warn("messages", "mark read failed", err);
    }
  }, []);

  const playVoicemail = useCallback(
    async (item: VoicemailRow) => {
      try {
        setPlayErrorById((prev) => {
          const next = { ...prev };
          delete next[item.id];
          return next;
        });
        // Coupe toute bande appel eventuelle + autre message (singleton).
        stopCallPlayback();
        const uri = await resolveUri(item);
        await toggleVoicemailPlayback(item.id, uri);
        await markReadIfNeeded(item);
      } catch (err) {
        log.error("messages", "play failed", err);
        stopVoicemailPlayback();
        setPlayErrorById((prev) => ({
          ...prev,
          [item.id]: "Lecture impossible. Verifie la connexion et reessaie.",
        }));
      }
    },
    [resolveUri, markReadIfNeeded],
  );

  const seekRatio = useCallback(
    async (item: VoicemailRow, ratio: number) => {
      if (!Number.isFinite(ratio)) return;
      try {
        stopCallPlayback();
        const uri = await resolveUri(item);
        const dur = Math.max(
          player.activeId === item.id && Number.isFinite(player.duration) ? player.duration : 0,
          Number(item.duration) || 0,
          1,
        );
        const target = Math.min(1, Math.max(0, ratio)) * dur;
        if (!Number.isFinite(target)) return;
        await ensureVoicemailPlaying(item.id, uri);
        seekVoicemailPlayback(target);
        await markReadIfNeeded(item);
      } catch (err) {
        log.warn("messages", "seek failed", err);
      }
    },
    [resolveUri, markReadIfNeeded, player.activeId, player.duration],
  );

  const skip = useCallback(
    async (item: VoicemailRow, delta: number) => {
      try {
        stopCallPlayback();
        const uri = await resolveUri(item);
        await ensureVoicemailPlaying(item.id, uri);
        skipVoicemailPlayback(delta);
        await markReadIfNeeded(item);
      } catch (err) {
        log.warn("messages", "skip failed", err);
      }
    },
    [resolveUri, markReadIfNeeded],
  );

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
        renderItem={({ item }) => (
          <VoicemailListItem
            item={item}
            player={player}
            playError={playErrorById[item.id] ?? null}
            onTogglePlay={() => void playVoicemail(item)}
            onSeekRatio={(ratio) => void seekRatio(item, ratio)}
            onSkip={(delta) => void skip(item, delta)}
          />
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate },
  empty: { color: colors.textMuted, textAlign: "center", marginTop: 48, paddingHorizontal: 24 },
});
