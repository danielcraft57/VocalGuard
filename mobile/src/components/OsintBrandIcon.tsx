import React from "react";
import { View, Text, StyleSheet } from "react-native";
import type { OsintBrandVisual } from "../utils/osintBrand";

type Props = {
  /** Visuel marque, ou null pour pastille transparente (reserve la place). */
  brand: OsintBrandVisual | null;
  /** Taille du cercle (px), alignee sur l icone direction. */
  size?: number;
};

/**
 * Pastille marque OSINT (operateurs + interim).
 * Sans info : cercle transparent de meme taille pour garder l alignement.
 */
export function OsintBrandIcon({ brand, size = 40 }: Props) {
  if (!brand) {
    return (
      <View
        style={[styles.slot, { width: size, height: size, borderRadius: size / 2 }]}
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
      />
    );
  }

  const len = brand.short.length;
  const fontSize = len > 3 ? size * 0.28 : len > 2 ? size * 0.32 : size * 0.4;

  return (
    <View
      style={[
        styles.badge,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: brand.bg,
        },
      ]}
      accessibilityLabel={brand.title}
      accessibilityRole="image"
    >
      <Text style={[styles.label, { color: brand.fg, fontSize }]} numberOfLines={1}>
        {brand.short}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  slot: {
    backgroundColor: "transparent",
  },
  badge: {
    alignItems: "center",
    justifyContent: "center",
  },
  label: {
    fontWeight: "800",
    letterSpacing: -0.4,
  },
});
