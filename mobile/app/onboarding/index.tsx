import React from "react";
import { View, Text, Pressable, StyleSheet, Image } from "react-native";
import { Link } from "expo-router";
import { colors } from "../../src/theme/colors";

/**
 * Accueil onboarding : scan QR ou saisie manuelle.
 */
export default function OnboardingIndex() {
  return (
    <View style={styles.container}>
      <Image
        source={require("../../assets/adaptive-icon.png")}
        style={styles.logo}
        accessibilityLabel="VocalGuard"
      />
      <Text style={styles.title}>Connecter VocalGuard</Text>
      <Text style={styles.subtitle}>Scannez le QR code depuis la page web App mobile.</Text>
      <Link href="/onboarding/scan" asChild>
        <Pressable style={styles.primary}>
          <Text style={styles.primaryText}>Scanner le QR code</Text>
        </Pressable>
      </Link>
      <Link href="/onboarding/manual" asChild>
        <Pressable style={styles.secondary}>
          <Text style={styles.secondaryText}>Saisie manuelle</Text>
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
    gap: 16,
  },
  logo: { width: 128, height: 128 },
  title: { color: colors.text, fontSize: 24, fontWeight: "700" },
  subtitle: { color: colors.textMuted, textAlign: "center" },
  primary: {
    backgroundColor: colors.primary,
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 10,
    marginTop: 12,
  },
  primaryText: { color: colors.white, fontWeight: "700" },
  secondary: { padding: 12 },
  secondaryText: { color: colors.textMuted },
});
