import React, { useCallback, useEffect, useState } from "react";
import { View, Text, Pressable, StyleSheet, ActivityIndicator, Alert } from "react-native";
import { Link, useRouter } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { clearCredentials, getStoredCredentials } from "../../src/services/credentials";
import { pingHealth, resolveConnectivityState } from "../../src/services/connectivity";
import { fetchMobileStats } from "../../src/services/stats";
import { getAppDb } from "../../src/db/getAppDb";
import { syncFromServer } from "../../src/services/sync";
import { colors } from "../../src/theme/colors";
import { icons } from "../../src/theme/icons";

/**
 * Reglages : confiance, sync manuelle, test connexion, re-appairage.
 */
export default function SettingsScreen() {
  const router = useRouter();
  const [baseUrl, setBaseUrl] = useState<string | null>(null);
  const [connLabel, setConnLabel] = useState("...");
  const [busy, setBusy] = useState(false);

  const refreshStatus = useCallback(async () => {
    const creds = await getStoredCredentials();
    setBaseUrl(creds.baseUrl);
    if (!creds.baseUrl) {
      setConnLabel("Non appaire");
      return;
    }
    const state = await resolveConnectivityState(creds.baseUrl);
    setConnLabel(state === "online" ? "En ligne" : state === "syncing" ? "Sync..." : "Hors ligne");
  }, []);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const resetPairing = async () => {
    await clearCredentials();
    router.replace("/onboarding");
  };

  const onTestConnection = async () => {
    setBusy(true);
    try {
      const creds = await getStoredCredentials();
      if (!creds.baseUrl || !creds.token) {
        Alert.alert("Appairage", "Configure d abord l appairage QR.");
        return;
      }
      const healthOk = await pingHealth(creds.baseUrl);
      const stats = await fetchMobileStats({ baseUrl: creds.baseUrl, token: creds.token });
      Alert.alert(
        "Connexion OK",
        `Serveur joignable.\nAppels aujourd hui : ${stats.calls_today}\nMessages non lus : ${stats.unread_voicemails}`,
      );
      if (!healthOk) {
        Alert.alert("Attention", "L API repond mais le health check a echoue.");
      }
      await refreshStatus();
    } catch (err) {
      Alert.alert("Erreur", err instanceof Error ? err.message : "Test impossible");
      setConnLabel("Hors ligne");
    } finally {
      setBusy(false);
    }
  };

  const onForceSync = async () => {
    setBusy(true);
    try {
      const creds = await getStoredCredentials();
      if (!creds.baseUrl || !creds.token) {
        Alert.alert("Appairage", "Configure d abord l appairage QR.");
        return;
      }
      const db = await getAppDb();
      const sync = await db.getFirstAsync<{ last_sync_at: string | null }>(
        "SELECT last_sync_at FROM sync_state WHERE id = 1",
      );
      const merged = await syncFromServer(db, { baseUrl: creds.baseUrl, token: creds.token }, sync?.last_sync_at ?? null);
      Alert.alert("Synchronisation", `${merged} element(s) mis a jour.`);
      await refreshStatus();
    } catch (err) {
      Alert.alert("Erreur", err instanceof Error ? err.message : "Sync echouee");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.infoCard}>
        <Text style={styles.infoLabel}>Serveur</Text>
        <Text style={styles.infoValue} numberOfLines={2}>
          {baseUrl ?? "Non configure"}
        </Text>
        <View style={styles.statusRow}>
          <View style={[styles.dot, connLabel === "En ligne" ? styles.dotOk : styles.dotKo]} />
          <Text style={styles.statusText}>{connLabel}</Text>
        </View>
      </View>

      <Pressable style={styles.row} onPress={onTestConnection} disabled={busy}>
        <MaterialCommunityIcons name={icons.wifi} size={22} color={colors.primary} />
        <Text style={styles.label}>Tester la connexion</Text>
        {busy ? <ActivityIndicator color={colors.primary} /> : null}
      </Pressable>

      <Pressable style={styles.row} onPress={onForceSync} disabled={busy}>
        <MaterialCommunityIcons name="sync" size={22} color={colors.primary} />
        <Text style={styles.label}>Forcer la synchronisation</Text>
      </Pressable>

      <Link href="/trusted" asChild>
        <Pressable style={styles.row}>
          <MaterialCommunityIcons name={icons.trusted} size={22} color={colors.primary} />
          <Text style={styles.label}>Personnes de confiance</Text>
        </Pressable>
      </Link>

      <Link href="/trusted/import" asChild>
        <Pressable style={styles.row}>
          <MaterialCommunityIcons name={icons.contacts} size={22} color={colors.primary} />
          <Text style={styles.label}>Importer des contacts</Text>
        </Pressable>
      </Link>

      <Pressable style={[styles.row, styles.dangerRow]} onPress={resetPairing}>
        <MaterialCommunityIcons name={icons.qrScan} size={22} color={colors.danger} />
        <Text style={[styles.label, styles.dangerText]}>Reconfigurer l appairage</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate, padding: 16, gap: 8 },
  infoCard: {
    backgroundColor: colors.slateLight,
    borderRadius: 12,
    padding: 16,
    marginBottom: 4,
  },
  infoLabel: { color: colors.textMuted, fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5 },
  infoValue: { color: colors.text, fontSize: 14, marginTop: 4 },
  statusRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 10 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  dotOk: { backgroundColor: colors.primary },
  dotKo: { backgroundColor: colors.danger },
  statusText: { color: colors.textMuted, fontSize: 13 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 16,
    backgroundColor: colors.slateLight,
    borderRadius: 12,
  },
  dangerRow: { marginTop: 8 },
  label: { color: colors.text, fontSize: 16, flex: 1 },
  dangerText: { color: colors.danger },
});
