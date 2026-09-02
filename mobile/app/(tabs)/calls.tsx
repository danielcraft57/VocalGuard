import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, FlatList, StyleSheet, RefreshControl, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { getStoredCredentials } from "../../src/services/credentials";
import { isApiUnauthorized } from "../../src/services/api";
import { OfflineBanner } from "../../src/components/OfflineBanner";
import { StatsBanner } from "../../src/components/StatsBanner";
import { CallStatusBadge } from "../../src/components/CallStatusBadge";
import { getAppDb } from "../../src/db/getAppDb";
import type { CallRow } from "../../src/db/schema";
import { resolveConnectivityState } from "../../src/services/connectivity";
import { log } from "../../src/services/log";
import { fetchMobileStats, MobileStats } from "../../src/services/stats";
import { syncFromServer } from "../../src/services/sync";
import { formatCallTime, formatDuration } from "../../src/utils/format";
import { navigateToDialer } from "../../src/utils/nav";
import { colors } from "../../src/theme/colors";
import { icons } from "../../src/theme/icons";

/**
 * Liste des appels avec stats dashboard, badges statut et sync offline.
 */
export default function CallsScreen() {
  const router = useRouter();
  const [calls, setCalls] = useState<CallRow[]>([]);
  const [stats, setStats] = useState<MobileStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [connState, setConnState] = useState<"online" | "offline" | "syncing">("offline");
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [pullRefreshing, setPullRefreshing] = useState(false);
  const lastSyncRef = useRef<string | null>(null);
  const refreshInFlight = useRef(false);
  const refreshSeq = useRef(0);

  const loadLocal = useCallback(async () => {
    const db = await getAppDb();
    const rows = await db.getAllAsync<CallRow>("SELECT * FROM calls ORDER BY call_time DESC");
    setCalls(rows);
    const sync = await db.getFirstAsync<{ last_sync_at: string | null }>(
      "SELECT last_sync_at FROM sync_state WHERE id = 1",
    );
    const at = sync?.last_sync_at ?? null;
    lastSyncRef.current = at;
    setLastSync(at);
  }, []);

  const loadStats = useCallback(async (baseUrl: string, token: string) => {
    if (!baseUrl || !token) {
      setStats(null);
      return;
    }
    setStatsLoading(true);
    try {
      const data = await fetchMobileStats({ baseUrl, token });
      setStats(data);
    } catch (err) {
      log.warn("calls", "stats failed", err);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  const refresh = useCallback(
    async (reason: string) => {
      if (refreshInFlight.current) {
        log.warn("calls", "refresh ignore (deja en cours)", { reason });
        return;
      }
      refreshInFlight.current = true;
      const seq = ++refreshSeq.current;
      if (reason === "pull") setPullRefreshing(true);
      setConnState("syncing");
      try {
        const { baseUrl, token } = await getStoredCredentials();
        const url = baseUrl ?? "";
        const tok = token ?? "";

        if (url && tok) {
          const db = await getAppDb();
          await syncFromServer(db, { baseUrl: url, token: tok }, lastSyncRef.current);
          await loadStats(url, tok);
        }

        await loadLocal();
        const next = await resolveConnectivityState(url);
        setConnState(next);
        log.info("calls", "refresh end", { seq, connState: next });
      } catch (err) {
        if (!isApiUnauthorized(err)) {
          log.error("calls", "refresh failed", { seq, err });
        }
        setConnState("offline");
      } finally {
        refreshInFlight.current = false;
        setPullRefreshing(false);
      }
    },
    [loadLocal, loadStats],
  );

  useEffect(() => {
    void (async () => {
      try {
        await loadLocal();
        await refresh("mount");
      } catch (err) {
        log.error("calls", "mount init failed", err);
        setConnState("offline");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- init once
  }, []);

  const renderCall = ({ item }: { item: CallRow }) => {
    const title = item.caller_name?.trim() || item.phone_number || "Inconnu";
    const subtitle = item.caller_name ? item.phone_number : null;
    const duration = formatDuration(item.duration);

    return (
      <Pressable
        style={styles.row}
        onPress={() => {
          if (item.phone_number) navigateToDialer(router, item.phone_number);
        }}
      >
        <View style={styles.iconWrap}>
          <MaterialCommunityIcons name={icons.tabCalls} size={22} color={colors.primary} />
        </View>
        <View style={styles.body}>
          <View style={styles.titleRow}>
            <Text style={styles.title} numberOfLines={1}>
              {title}
            </Text>
            <Text style={styles.time}>{formatCallTime(item.call_time)}</Text>
          </View>
          {subtitle ? (
            <Text style={styles.subtitle} numberOfLines={1}>
              {subtitle}
            </Text>
          ) : null}
          <View style={styles.metaRow}>
            <CallStatusBadge status={item.status} />
            {duration ? <Text style={styles.duration}>{duration}</Text> : null}
          </View>
        </View>
      </Pressable>
    );
  };

  return (
    <View style={styles.container}>
      <OfflineBanner state={connState} lastSyncLabel={lastSync ? `sync ${lastSync}` : undefined} />
      <StatsBanner
        stats={stats}
        loading={statsLoading}
        onPressMessages={() => router.push("/(tabs)/messages")}
      />
      <FlatList
        data={calls}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl
            refreshing={pullRefreshing}
            onRefresh={() => void refresh("pull")}
            tintColor={colors.primary}
          />
        }
        ListEmptyComponent={
          <View style={styles.emptyWrap}>
            <MaterialCommunityIcons name={icons.tabCalls} size={48} color={colors.neutral400} />
            <Text style={styles.emptyTitle}>Aucun appel en cache</Text>
            <Text style={styles.emptyHint}>Tire vers le bas pour synchroniser avec le serveur.</Text>
            <Pressable style={styles.emptyBtn} onPress={() => void refresh("empty")}>
              <Text style={styles.emptyBtnText}>Synchroniser</Text>
            </Pressable>
          </View>
        }
        renderItem={renderCall}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate },
  row: {
    flexDirection: "row",
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.slateLight,
    gap: 12,
  },
  iconWrap: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.slateLight,
    alignItems: "center",
    justifyContent: "center",
  },
  body: { flex: 1, minWidth: 0 },
  titleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  title: { color: colors.text, fontSize: 16, fontWeight: "600", flex: 1 },
  time: { color: colors.textMuted, fontSize: 12 },
  subtitle: { color: colors.textMuted, fontSize: 13, marginTop: 2 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 6 },
  duration: { color: colors.textMuted, fontSize: 12 },
  emptyWrap: { alignItems: "center", paddingHorizontal: 32, paddingTop: 48, gap: 8 },
  emptyTitle: { color: colors.text, fontSize: 17, fontWeight: "600", marginTop: 8 },
  emptyHint: { color: colors.textMuted, textAlign: "center", lineHeight: 20 },
  emptyBtn: {
    marginTop: 12,
    backgroundColor: colors.primary,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 999,
  },
  emptyBtnText: { color: colors.slate, fontWeight: "700" },
});
