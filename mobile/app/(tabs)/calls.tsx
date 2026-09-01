import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, FlatList, StyleSheet, RefreshControl } from "react-native";
import { getStoredCredentials } from "../../src/services/credentials";
import { OfflineBanner } from "../../src/components/OfflineBanner";
import { getAppDb } from "../../src/db/getAppDb";
import type { CallRow } from "../../src/db/schema";
import { resolveConnectivityState } from "../../src/services/connectivity";
import { log } from "../../src/services/log";
import { syncFromServer } from "../../src/services/sync";
import { colors } from "../../src/theme/colors";

/**
 * Liste des appels (cache SQLite + refresh LAN).
 */
export default function CallsScreen() {
  const [calls, setCalls] = useState<CallRow[]>([]);
  const [connState, setConnState] = useState<"online" | "offline" | "syncing">("offline");
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [pullRefreshing, setPullRefreshing] = useState(false);
  const lastSyncRef = useRef<string | null>(null);
  const refreshInFlight = useRef(false);
  const refreshSeq = useRef(0);

  const loadLocal = useCallback(async () => {
    log.debug("calls", "loadLocal start");
    const db = await getAppDb();
    const rows = await db.getAllAsync<CallRow>("SELECT * FROM calls ORDER BY call_time DESC");
    setCalls(rows);
    const sync = await db.getFirstAsync<{ last_sync_at: string | null }>(
      "SELECT last_sync_at FROM sync_state WHERE id = 1",
    );
    const at = sync?.last_sync_at ?? null;
    lastSyncRef.current = at;
    setLastSync(at);
    log.debug("calls", "loadLocal done", { rows: rows.length, lastSync: at });
  }, []);

  const refresh = useCallback(async (reason: string) => {
    if (refreshInFlight.current) {
      log.warn("calls", "refresh ignore (deja en cours)", { reason });
      return;
    }
    refreshInFlight.current = true;
    const seq = ++refreshSeq.current;
    log.info("calls", "refresh start", { reason, seq, since: lastSyncRef.current });
    if (reason === "pull") setPullRefreshing(true);
    setConnState("syncing");
    try {
      const { baseUrl, token } = await getStoredCredentials();
      const url = baseUrl ?? "";
      const tok = token ?? "";
      log.debug("calls", "credentials", {
        hasBaseUrl: Boolean(url),
        hasToken: Boolean(tok),
        baseUrl: url || "(vide)",
      });

      if (url && tok) {
        const db = await getAppDb();
        const merged = await syncFromServer(db, { baseUrl: url, token: tok }, lastSyncRef.current);
        log.info("calls", "syncFromServer ok", { seq, merged });
      } else {
        log.warn("calls", "sync saute (pas de token / url)", { seq });
      }

      await loadLocal();
      const next = await resolveConnectivityState(url);
      setConnState(next);
      log.info("calls", "refresh end", { seq, connState: next });
    } catch (err) {
      log.error("calls", "refresh failed", { seq, err });
      setConnState("offline");
    } finally {
      refreshInFlight.current = false;
      setPullRefreshing(false);
    }
  }, [loadLocal]);

  // Montage unique : ne PAS dependre de refresh/lastSync sinon boucle infinie.
  useEffect(() => {
    log.info("calls", "mount init");
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

  return (
    <View style={styles.container}>
      <OfflineBanner state={connState} lastSyncLabel={lastSync ? `sync ${lastSync}` : undefined} />
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
        ListEmptyComponent={<Text style={styles.empty}>Aucun appel en cache</Text>}
        renderItem={({ item }) => (
          <View style={styles.row}>
            <Text style={styles.phone}>{item.phone_number}</Text>
            <Text style={styles.meta}>{item.caller_name ?? item.status ?? ""}</Text>
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate },
  row: { padding: 16, borderBottomWidth: 1, borderBottomColor: colors.slateLight },
  phone: { color: colors.text, fontSize: 16, fontWeight: "600" },
  meta: { color: colors.textMuted, marginTop: 4 },
  empty: { color: colors.textMuted, textAlign: "center", marginTop: 48 },
});
