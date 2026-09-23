import React from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from "react-native";
import type { CallOsintLite } from "../db/schema";
import { buildOsintChips } from "../utils/osintChips";
import { colors } from "../theme/colors";

type Props = {
  osint: CallOsintLite | null;
  phoneLabel?: string;
  /** Rafraichit le profil OSINT (meme action que le web). */
  onRefresh?: () => void;
  refreshing?: boolean;
};

/**
 * Panneau OSINT aligne web : overline + chips + bouton Rafraichir.
 * Pas de carte separee (le cadre principal reste Sous-titres).
 */
export function CallOsintPanel({ osint, phoneLabel, onRefresh, refreshing }: Props) {
  const chips = buildOsintChips(osint);

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>OSINT</Text>
      {!osint ? (
        <Text style={styles.empty}>
          Pas de profil OSINT en base{phoneLabel ? ` pour ${phoneLabel}` : ""}.
        </Text>
      ) : (
        <View style={styles.chips}>
          {chips.map((c) => (
            <View
              key={c.key}
              style={[
                styles.chip,
                c.variant === "primary" && styles.chipPrimary,
                c.variant === "warn" && styles.chipWarn,
                c.variant === "danger" && styles.chipDanger,
              ]}
            >
              <Text
                style={[
                  styles.chipText,
                  c.variant === "primary" && styles.chipTextPrimary,
                  c.variant === "warn" && styles.chipTextWarn,
                  c.variant === "danger" && styles.chipTextDanger,
                ]}
              >
                {c.label}
              </Text>
            </View>
          ))}
        </View>
      )}
      {onRefresh ? (
        <Pressable
          style={styles.refreshBtn}
          onPress={onRefresh}
          disabled={refreshing}
          accessibilityRole="button"
          accessibilityLabel="Rafraichir OSINT"
        >
          {refreshing ? (
            <ActivityIndicator size="small" color={colors.primary} />
          ) : (
            <Text style={styles.refreshText}>Rafraichir OSINT</Text>
          )}
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8 },
  title: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 1.2,
  },
  empty: { color: colors.textMuted, fontSize: 13, lineHeight: 18 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "rgba(148,163,184,0.35)",
    backgroundColor: "transparent",
  },
  chipPrimary: {
    borderColor: "rgba(34,197,94,0.45)",
    backgroundColor: "rgba(34,197,94,0.08)",
  },
  chipWarn: {
    borderColor: "rgba(251,191,36,0.45)",
    backgroundColor: "rgba(251,191,36,0.1)",
  },
  chipDanger: {
    borderColor: "rgba(239,68,68,0.45)",
    backgroundColor: "rgba(239,68,68,0.12)",
  },
  chipText: { color: colors.neutral200, fontSize: 12, fontWeight: "600" },
  chipTextPrimary: { color: colors.primary },
  chipTextWarn: { color: "#fbbf24" },
  chipTextDanger: { color: colors.danger },
  refreshBtn: {
    alignSelf: "flex-start",
    marginTop: 4,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(34,197,94,0.4)",
    minWidth: 120,
    alignItems: "center",
  },
  refreshText: { color: colors.primary, fontSize: 13, fontWeight: "700" },
});
