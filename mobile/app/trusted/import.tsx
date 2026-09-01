import React, { useState } from "react";
import { View, Text, FlatList, Pressable, StyleSheet, Alert } from "react-native";
import { getStoredCredentials } from "../../src/services/credentials";
import { buildTrustedImportPayload, DeviceContact, filterCallableContacts } from "../../src/services/contactsImport";
import { apiPost } from "../../src/services/api";
import { colors } from "../../src/theme/colors";

const SAMPLE: DeviceContact[] = [
  { id: "1", name: "Alice Martin", phoneNumbers: ["06 12 34 56 78"] },
  { id: "2", name: "Bob Dupont", phoneNumbers: ["+33 6 98 76 54 32"] },
];

/**
 * Import contacts vers personnes de confiance (expo-contacts en prod, sample en dev).
 */
export default function TrustedImportScreen() {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const contacts = filterCallableContacts(SAMPLE);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onImport = async () => {
    const picked = contacts.filter((c) => c.id && selected.has(c.id));
    const payload = buildTrustedImportPayload(picked);
    const { baseUrl, token } = await getStoredCredentials();
    if (!baseUrl || !token) {
      Alert.alert("Offline", "Appairage requis.");
      return;
    }
    try {
      const res = await apiPost<{ imported: number }>({ baseUrl, token }, "/public/trusted/import", {
        contacts: payload,
      });
      Alert.alert("Import", `${res.imported} contact(s) ajoute(s).`);
    } catch (err) {
      Alert.alert("Erreur", err instanceof Error ? err.message : "Import impossible");
    }
  };

  return (
    <View style={styles.container}>
      <FlatList
        data={contacts}
        keyExtractor={(item) => item.id ?? item.name}
        renderItem={({ item }) => (
          <Pressable style={styles.row} onPress={() => item.id && toggle(item.id)}>
            <Text style={styles.name}>{item.name}</Text>
            <Text style={styles.check}>{item.id && selected.has(item.id) ? "[x]" : "[ ]"}</Text>
          </Pressable>
        )}
      />
      <Pressable style={styles.cta} onPress={onImport} disabled={selected.size === 0}>
        <Text style={styles.ctaText}>Ajouter {selected.size} personne(s) de confiance</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate },
  row: { flexDirection: "row", justifyContent: "space-between", padding: 16, borderBottomWidth: 1, borderBottomColor: colors.slateLight },
  name: { color: colors.text },
  check: { color: colors.primary },
  cta: { backgroundColor: colors.primary, margin: 16, padding: 16, borderRadius: 10, alignItems: "center" },
  ctaText: { color: colors.white, fontWeight: "700" },
});
