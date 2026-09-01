import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors } from "../../src/theme/colors";

/** Liste locale personnes de confiance (sync via API). */
export default function TrustedListScreen() {
  return (
    <View style={styles.container}>
      <Text style={styles.text}>Liste synchronisee depuis le serveur VocalGuard.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate, padding: 20 },
  text: { color: colors.textMuted },
});
