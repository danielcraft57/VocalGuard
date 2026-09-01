import React from "react";
import { View, Pressable, Text, StyleSheet } from "react-native";
import { colors } from "../theme/colors";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"];

export interface DialPadProps {
  phone: string;
  onChange: (value: string) => void;
  onCall?: () => void;
  disabled?: boolean;
}

/**
 * Pavé numerique plein ecran pour appels sortants.
 */
export function DialPad({ phone, onChange, onCall, disabled = false }: DialPadProps) {
  const append = (digit: string) => {
    if (!disabled) onChange(phone + digit);
  };

  const backspace = () => {
    if (!disabled) onChange(phone.slice(0, -1));
  };

  return (
    <View style={styles.wrap}>
      <Text style={styles.display}>{phone || "Composer un numero"}</Text>
      <View style={styles.grid}>
        {KEYS.map((k) => (
          <Pressable key={k} style={styles.key} onPress={() => append(k)} disabled={disabled}>
            <Text style={styles.keyText}>{k}</Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.actions}>
        <Pressable style={styles.secondary} onPress={backspace} disabled={disabled}>
          <Text style={styles.secondaryText}>Effacer</Text>
        </Pressable>
        <Pressable
          style={[styles.callBtn, disabled ? styles.callDisabled : null]}
          onPress={onCall}
          disabled={disabled || !phone.trim()}
        >
          <Text style={styles.callText}>Appeler</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, padding: 16, backgroundColor: colors.slate },
  display: {
    color: colors.text,
    fontSize: 28,
    textAlign: "center",
    marginVertical: 24,
    minHeight: 40,
  },
  grid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "center", gap: 12 },
  key: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.slateLight,
    alignItems: "center",
    justifyContent: "center",
  },
  keyText: { color: colors.white, fontSize: 24, fontWeight: "600" },
  actions: { flexDirection: "row", justifyContent: "center", gap: 16, marginTop: 24 },
  secondary: { padding: 14 },
  secondaryText: { color: colors.textMuted },
  callBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: 32,
    paddingVertical: 14,
    borderRadius: 999,
  },
  callDisabled: { opacity: 0.5 },
  callText: { color: colors.white, fontWeight: "700", fontSize: 16 },
});
