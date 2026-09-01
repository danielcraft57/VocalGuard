import React from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { Link, useRouter } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { colors } from "../../src/theme/colors";
import { icons } from "../../src/theme/icons";

/**
 * Ecran victoire post-appairage.
 */
export default function OnboardingSuccessScreen() {
  const router = useRouter();

  return (
    <View style={styles.container}>
      <MaterialCommunityIcons name={icons.syncOk} size={72} color={colors.primary} />
      <Text style={styles.title}>Telephone pret</Text>
      <Text style={styles.subtitle}>Connexion LAN verifiee. Vous pouvez consulter appels et messages.</Text>
      <Pressable style={styles.primary} onPress={() => router.replace("/(tabs)/calls")}>
        <Text style={styles.primaryText}>Continuer</Text>
      </Pressable>
      <Link href="/trusted/import" asChild>
        <Pressable style={styles.secondary}>
          <Text style={styles.secondaryText}>Importer vos contacts de confiance</Text>
        </Pressable>
      </Link>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.slate,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 12,
  },
  title: { color: colors.text, fontSize: 24, fontWeight: "700" },
  subtitle: { color: colors.textMuted, textAlign: "center" },
  primary: {
    backgroundColor: colors.primary,
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 10,
    marginTop: 8,
  },
  primaryText: { color: colors.white, fontWeight: "700" },
  secondary: { padding: 12 },
  secondaryText: { color: colors.primary },
});
