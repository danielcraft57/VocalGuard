import React from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import type { MobileStats } from "../services/stats";
import { colors } from "../theme/colors";
import { icons } from "../theme/icons";

type StatsBannerProps = {
  stats: MobileStats | null;
  loading?: boolean;
  onPressMessages?: () => void;
};

/**
 * Bandeau resume dashboard (appels du jour, messages non lus).
 */
export function StatsBanner({ stats, loading, onPressMessages }: StatsBannerProps) {
  if (loading && !stats) {
    return (
      <View style={styles.container}>
        <Text style={styles.loading}>Chargement des stats...</Text>
      </View>
    );
  }
  if (!stats) return null;

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <MaterialCommunityIcons name={icons.tabCalls} size={22} color={colors.primary} />
        <View>
          <Text style={styles.value}>{stats.calls_today}</Text>
          <Text style={styles.label}>Appels aujourd hui</Text>
        </View>
      </View>
      <Pressable
        style={({ pressed }) => [styles.card, pressed && styles.pressed]}
        onPress={onPressMessages}
        disabled={!onPressMessages}
      >
        <MaterialCommunityIcons name={icons.tabMessages} size={22} color="#f59e0b" />
        <View>
          <Text style={styles.value}>{stats.unread_voicemails}</Text>
          <Text style={styles.label}>Messages non lus</Text>
        </View>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    gap: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  card: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: colors.slateLight,
    borderRadius: 12,
    padding: 12,
  },
  pressed: { opacity: 0.85 },
  value: { color: colors.text, fontSize: 20, fontWeight: "700" },
  label: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  loading: { color: colors.textMuted, padding: 12, textAlign: "center", flex: 1 },
});
