import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors } from "../theme/colors";

export type CallStatusKind = "answered" | "missed" | "blocked" | "ringing" | "completed" | "other";

/**
 * Determine le type visuel d un statut d appel backend.
 *
 * @param status Statut brut API.
 * @returns Categorie pour le badge.
 */
export function resolveCallStatusKind(status: string | null | undefined): CallStatusKind {
  const s = (status ?? "").toLowerCase();
  if (s === "answered" || s === "completed") return "answered";
  if (s === "missed") return "missed";
  if (s === "blocked") return "blocked";
  if (s === "ringing") return "ringing";
  return "other";
}

const BADGE_STYLES: Record<CallStatusKind, { label: string; bg: string; fg: string }> = {
  answered: { label: "Repondu", bg: "rgba(34, 197, 94, 0.15)", fg: colors.primary },
  missed: { label: "Manque", bg: "rgba(245, 158, 11, 0.15)", fg: "#f59e0b" },
  blocked: { label: "Bloque", bg: "rgba(239, 68, 68, 0.15)", fg: colors.danger },
  ringing: { label: "Sonnerie", bg: "rgba(14, 165, 233, 0.15)", fg: "#0ea5e9" },
  completed: { label: "Termine", bg: "rgba(34, 197, 94, 0.15)", fg: colors.primary },
  other: { label: "Appel", bg: "rgba(148, 163, 184, 0.15)", fg: colors.textMuted },
};

type CallStatusBadgeProps = {
  status: string | null | undefined;
};

/**
 * Badge Material-like pour le statut d un appel.
 */
export function CallStatusBadge({ status }: CallStatusBadgeProps) {
  const kind = resolveCallStatusKind(status);
  const style = BADGE_STYLES[kind];
  const label = kind === "other" && status ? status : style.label;

  return (
    <View style={[styles.badge, { backgroundColor: style.bg }]}>
      <Text style={[styles.text, { color: style.fg }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 999,
    alignSelf: "flex-start",
  },
  text: {
    fontSize: 11,
    fontWeight: "600",
    textTransform: "capitalize",
  },
});
