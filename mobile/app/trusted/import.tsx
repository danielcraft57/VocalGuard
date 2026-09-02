import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View,
  Text,
  FlatList,
  Pressable,
  StyleSheet,
  Alert,
  ActivityIndicator,
  TextInput,
  Platform,
} from "react-native";
import { useRouter } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import * as Contacts from "expo-contacts";
import { getStoredCredentials } from "../../src/services/credentials";
import {
  buildTrustedImportPayload,
  contactKey,
  DeviceContact,
  filterCallableContacts,
} from "../../src/services/contactsImport";
import { apiPost } from "../../src/services/api";
import { formatPhone } from "../../src/utils/format";
import { colors } from "../../src/theme/colors";
import { icons } from "../../src/theme/icons";

const SAMPLE: DeviceContact[] = [
  { id: "1", name: "Alice Martin", phoneNumbers: ["06 12 34 56 78"] },
  { id: "2", name: "Bob Dupont", phoneNumbers: ["+33 6 98 76 54 32"] },
];

/**
 * Charge les contacts du telephone (expo-contacts) ou echantillon web.
 */
async function loadDeviceContacts(): Promise<DeviceContact[]> {
  if (Platform.OS === "web") return SAMPLE;

  const { status } = await Contacts.requestPermissionsAsync();
  if (status !== "granted") {
    throw new Error("Permission contacts refusee.");
  }

  const all: Contacts.Contact[] = [];
  let pageOffset = 0;
  const pageSize = 500;
  while (true) {
    const { data, hasNextPage } = await Contacts.getContactsAsync({
      fields: [Contacts.Fields.PhoneNumbers, Contacts.Fields.Name],
      sort: Contacts.SortTypes.FirstName,
      pageSize,
      pageOffset,
    });
    all.push(...data);
    if (!hasNextPage) break;
    pageOffset += pageSize;
  }

  return all
    .filter((c) => c.phoneNumbers && c.phoneNumbers.length > 0)
    .map((c) => ({
      id: "id" in c && c.id ? String(c.id) : undefined,
      name: c.name?.trim() || "Sans nom",
      phoneNumbers: c.phoneNumbers!.map((p) => p.number ?? "").filter(Boolean),
    }));
}

/**
 * Import contacts vers personnes de confiance.
 */
export default function TrustedImportScreen() {
  const router = useRouter();
  const [contacts, setContacts] = useState<DeviceContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const raw = await loadDeviceContacts();
      setContacts(filterCallableContacts(raw));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible de lire les contacts");
      setContacts([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return contacts;
    return contacts.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.phoneNumbers.some((p) => p.replace(/\D/g, "").includes(q.replace(/\D/g, ""))),
    );
  }, [contacts, query]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    setSelected(new Set(filtered.map((c) => contactKey(c))));
  };

  const onImport = async () => {
    const picked = contacts.filter((c) => selected.has(contactKey(c)));
    const payload = buildTrustedImportPayload(picked);
    if (payload.length === 0) return;

    const { baseUrl, token } = await getStoredCredentials();
    if (!baseUrl || !token) {
      Alert.alert("Appairage", "Configure d abord l appairage QR.");
      return;
    }

    setImporting(true);
    try {
      const res = await apiPost<{ imported: number; skipped?: number }>(
        { baseUrl, token },
        "/public/trusted/import",
        { contacts: payload },
      );
      const skipped = res.skipped ? ` (${res.skipped} ignore(s))` : "";
      Alert.alert("Import termine", `${res.imported} contact(s) ajoute(s)${skipped}.`, [
        { text: "Voir la liste", onPress: () => router.replace("/trusted") },
        { text: "OK" },
      ]);
      setSelected(new Set());
    } catch (err) {
      Alert.alert("Erreur", err instanceof Error ? err.message : "Import impossible");
    } finally {
      setImporting(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.primary} size="large" />
        <Text style={styles.loadingText}>Lecture des contacts...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.searchRow}>
        <MaterialCommunityIcons name="magnify" size={20} color={colors.textMuted} />
        <TextInput
          style={styles.searchInput}
          placeholder="Rechercher un contact..."
          placeholderTextColor={colors.textMuted}
          value={query}
          onChangeText={setQuery}
          autoCorrect={false}
        />
      </View>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
          <Pressable onPress={() => void load()}>
            <Text style={styles.retryText}>Reessayer</Text>
          </Pressable>
        </View>
      ) : null}

      <View style={styles.toolbar}>
        <Text style={styles.count}>
          {selected.size} selectionne{selected.size > 1 ? "s" : ""} sur {filtered.length}
        </Text>
        <Pressable onPress={selectAll} disabled={filtered.length === 0}>
          <Text style={styles.selectAll}>Tout selectionner</Text>
        </Pressable>
      </View>

      <FlatList
        data={filtered}
        keyExtractor={(item) => contactKey(item)}
        ListEmptyComponent={
          <Text style={styles.empty}>
            {query ? "Aucun contact ne correspond." : "Aucun contact avec numero valide."}
          </Text>
        }
        renderItem={({ item }) => {
          const id = contactKey(item);
          const checked = selected.has(id);
          const phone = item.phoneNumbers[0] ?? "";
          return (
            <Pressable style={styles.row} onPress={() => toggle(id)}>
              <MaterialCommunityIcons
                name={checked ? "checkbox-marked" : "checkbox-blank-outline"}
                size={24}
                color={checked ? colors.primary : colors.textMuted}
              />
              <View style={styles.body}>
                <Text style={styles.name}>{item.name}</Text>
                <Text style={styles.phone}>{formatPhone(phone)}</Text>
                {item.phoneNumbers.length > 1 ? (
                  <Text style={styles.multi}>+{item.phoneNumbers.length - 1} autre(s) numero(s)</Text>
                ) : null}
              </View>
            </Pressable>
          );
        }}
      />

      <Pressable
        style={[styles.cta, (selected.size === 0 || importing) && styles.ctaDisabled]}
        onPress={onImport}
        disabled={selected.size === 0 || importing}
      >
        {importing ? (
          <ActivityIndicator color={colors.white} />
        ) : (
          <>
            <MaterialCommunityIcons name={icons.trusted} size={20} color={colors.white} />
            <Text style={styles.ctaText}>Ajouter {selected.size} personne(s) de confiance</Text>
          </>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate },
  center: { flex: 1, backgroundColor: colors.slate, alignItems: "center", justifyContent: "center", gap: 12 },
  loadingText: { color: colors.textMuted },
  searchRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    margin: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: colors.slateLight,
    borderRadius: 10,
  },
  searchInput: { flex: 1, color: colors.text, fontSize: 16 },
  toolbar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingBottom: 8,
  },
  count: { color: colors.textMuted, fontSize: 13 },
  selectAll: { color: colors.primary, fontSize: 13, fontWeight: "600" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.slateLight,
  },
  body: { flex: 1 },
  name: { color: colors.text, fontSize: 16, fontWeight: "600" },
  phone: { color: colors.textMuted, fontSize: 13, marginTop: 2 },
  multi: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  empty: { color: colors.textMuted, textAlign: "center", marginTop: 48, paddingHorizontal: 24 },
  cta: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: colors.primary,
    margin: 16,
    padding: 16,
    borderRadius: 12,
  },
  ctaDisabled: { opacity: 0.5 },
  ctaText: { color: colors.white, fontWeight: "700", fontSize: 15 },
  errorBox: { marginHorizontal: 16, marginBottom: 8, padding: 12, backgroundColor: colors.slateLight, borderRadius: 8 },
  errorText: { color: colors.danger, marginBottom: 6 },
  retryText: { color: colors.primary, fontWeight: "600" },
});
