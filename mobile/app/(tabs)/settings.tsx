import React from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { Link, useRouter } from "expo-router";
import { clearCredentials } from "../../src/services/credentials";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { colors } from "../../src/theme/colors";
import { icons } from "../../src/theme/icons";

/**
 * Reglages : confiance, re-appairage, deconnexion.
 */
export default function SettingsScreen() {
  const router = useRouter();

  const resetPairing = async () => {
    await clearCredentials();
    router.replace("/onboarding");
  };

  return (
    <View style={styles.container}>
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
      <Pressable style={styles.row} onPress={resetPairing}>
        <MaterialCommunityIcons name={icons.qrScan} size={22} color={colors.danger} />
        <Text style={styles.label}>Reconfigurer l appairage</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate, padding: 16, gap: 8 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 16,
    backgroundColor: colors.slateLight,
    borderRadius: 12,
  },
  label: { color: colors.text, fontSize: 16 },
});
