import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  RefreshControl,
  Pressable,
  Alert,
  ActivityIndicator,
} from "react-native";
import { Link, useRouter } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { getStoredCredentials } from "../../src/services/credentials";
import { getAppDb } from "../../src/db/getAppDb";
import { log } from "../../src/services/log";
import {
  cacheTrustedContacts,
  fetchTrustedList,
  loadTrustedFromCache,
  removeTrustedContact,
  TrustedContact,
} from "../../src/services/trusted";
import { formatPhone } from "../../src/utils/format";
import { navigateToDialer } from "../../src/utils/nav";
import { colors } from "../../src/theme/colors";
import { icons } from "../../src/theme/icons";

/**
 * Liste des personnes de confiance synchronisee avec le serveur.
 */
export default function TrustedListScreen() {
  const router = useRouter();
  const [rows, setRows] = useState<TrustedContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [removingPhone, setRemovingPhone] = useState<string | null>(null);

  const load = useCallback(async (fromPull = false) => {
    if (fromPull) setRefreshing(true);
    else setLoading(true);
    try {
      const creds = await getStoredCredentials();
      if (!creds.baseUrl || !creds.token) {
        setRows([]);
        return;
      }
      const config = { baseUrl: creds.baseUrl, token: creds.token };
      try {
        const remote = await fetchTrustedList(config);
        const db = await getAppDb();
        await cacheTrustedContacts(db, remote);
        setRows(remote);
      } catch (err) {
        log.warn("trusted", "fetch remote failed, cache local", err);
        const db = await getAppDb();
        setRows(await loadTrustedFromCache(db));
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onRemove = (item: TrustedContact) => {
    Alert.alert(
      "Retirer de la confiance",
      `Retirer ${item.name ?? formatPhone(item.phone_number)} de la liste blanche ?`,
      [
        { text: "Annuler", style: "cancel" },
        {
          text: "Retirer",
          style: "destructive",
          onPress: () => {
            void (async () => {
              setRemovingPhone(item.phone_number);
              try {
                const creds = await getStoredCredentials();
                if (!creds.baseUrl || !creds.token) {
                  Alert.alert("Appairage", "Configure d abord l appairage QR.");
                  return;
                }
                await removeTrustedContact(
                  { baseUrl: creds.baseUrl, token: creds.token },
                  item.phone_number,
                );
                setRows((prev) => prev.filter((r) => r.phone_number !== item.phone_number));
                const db = await getAppDb();
                await db.runAsync("DELETE FROM trusted_contacts WHERE phone_number = ?", [
                  item.phone_number,
                ]);
              } catch (err) {
                Alert.alert("Erreur", err instanceof Error ? err.message : "Suppression impossible");
              } finally {
                setRemovingPhone(null);
              }
            })();
          },
        },
      ],
    );
  };

  const onCall = (phone: string) => {
    navigateToDialer(router, phone);
  };

  if (loading && rows.length === 0) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.primary} size="large" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={rows}
        keyExtractor={(item) => item.phone_number}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor={colors.primary}
          />
        }
        ListHeaderComponent={
          <View style={styles.header}>
            <Text style={styles.headerText}>
              {rows.length} personne{rows.length > 1 ? "s" : ""} de confiance
            </Text>
            <Link href="/trusted/import" asChild>
              <Pressable style={styles.importBtn}>
                <MaterialCommunityIcons name={icons.contacts} size={18} color={colors.slate} />
                <Text style={styles.importBtnText}>Importer</Text>
              </Pressable>
            </Link>
          </View>
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <MaterialCommunityIcons name={icons.trusted} size={48} color={colors.neutral400} />
            <Text style={styles.emptyTitle}>Aucune personne de confiance</Text>
            <Text style={styles.emptyHint}>
              Importe des contacts depuis ton telephone pour les ajouter a la liste blanche VocalGuard.
            </Text>
            <Link href="/trusted/import" asChild>
              <Pressable style={styles.emptyCta}>
                <Text style={styles.emptyCtaText}>Importer des contacts</Text>
              </Pressable>
            </Link>
          </View>
        }
        renderItem={({ item }) => {
          const busy = removingPhone === item.phone_number;
          return (
            <View style={styles.row}>
              <View style={styles.avatar}>
                <MaterialCommunityIcons name={icons.trusted} size={22} color={colors.primary} />
              </View>
              <View style={styles.body}>
                <Text style={styles.name}>{item.name ?? "Sans nom"}</Text>
                <Text style={styles.phone}>{formatPhone(item.phone_number)}</Text>
              </View>
              <Pressable
                style={styles.iconBtn}
                onPress={() => onCall(item.phone_number)}
                accessibilityLabel="Appeler"
              >
                <MaterialCommunityIcons name="phone" size={22} color={colors.primary} />
              </Pressable>
              <Pressable
                style={styles.iconBtn}
                onPress={() => onRemove(item)}
                disabled={busy}
                accessibilityLabel="Retirer"
              >
                {busy ? (
                  <ActivityIndicator color={colors.danger} size="small" />
                ) : (
                  <MaterialCommunityIcons name="close-circle-outline" size={22} color={colors.danger} />
                )}
              </Pressable>
            </View>
          );
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate },
  center: { flex: 1, backgroundColor: colors.slate, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  headerText: { color: colors.textMuted, fontSize: 13 },
  importBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: colors.primary,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
  },
  importBtnText: { color: colors.slate, fontWeight: "700", fontSize: 13 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.slateLight,
    gap: 10,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.slateLight,
    alignItems: "center",
    justifyContent: "center",
  },
  body: { flex: 1, minWidth: 0 },
  name: { color: colors.text, fontSize: 16, fontWeight: "600" },
  phone: { color: colors.textMuted, fontSize: 13, marginTop: 2 },
  iconBtn: { padding: 6 },
  empty: { alignItems: "center", paddingHorizontal: 32, paddingTop: 48, gap: 8 },
  emptyTitle: { color: colors.text, fontSize: 17, fontWeight: "600", marginTop: 8 },
  emptyHint: { color: colors.textMuted, textAlign: "center", lineHeight: 20 },
  emptyCta: {
    marginTop: 12,
    backgroundColor: colors.primary,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 999,
  },
  emptyCtaText: { color: colors.slate, fontWeight: "700" },
});
