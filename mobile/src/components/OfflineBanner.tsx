import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { colors } from "../theme/colors";
import { icons } from "../theme/icons";
import type { ConnectivityState } from "../services/connectivity";

export interface OfflineBannerProps {
  state: ConnectivityState;
  lastSyncLabel?: string;
}

/**
 * Bandeau discret etat reseau / sync.
 */
export function OfflineBanner({ state, lastSyncLabel }: OfflineBannerProps) {
  if (state === "online") return null;

  const isOffline = state === "offline";
  const label = isOffline
    ? `Donnees du cache${lastSyncLabel ? ` · ${lastSyncLabel}` : ""}`
    : "Synchronisation en cours...";

  return (
    <View style={[styles.banner, isOffline ? styles.offline : styles.syncing]}>
      <MaterialCommunityIcons
        name={isOffline ? icons.offline : icons.syncOk}
        size={18}
        color={colors.white}
      />
      <Text style={styles.text}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  offline: { backgroundColor: colors.slateLight },
  syncing: { backgroundColor: colors.primaryDark },
  text: { color: colors.white, fontSize: 13 },
});
