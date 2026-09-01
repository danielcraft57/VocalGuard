import React, { useState } from "react";
import { View, Text, TextInput, Pressable, StyleSheet, Alert } from "react-native";
import { useRouter } from "expo-router";
import { claimPairing } from "../../src/services/api";
import { parsePairUri } from "../../src/services/pairing";
import { saveCredentials } from "../_layout";
import { colors } from "../../src/theme/colors";

/**
 * Fallback saisie URL + code 8 caracteres.
 */
export default function ManualPairingScreen() {
  const router = useRouter();
  const [host, setHost] = useState("https://vocalguard.danielcraft.fr");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const onSubmit = async () => {
    setBusy(true);
    try {
      const encodedHost = encodeURIComponent(host.replace(/\/$/, ""));
      const parsed = parsePairUri(`vocalguard://pair?v=1&host=${encodedHost}&code=${code.trim()}`);
      if (!parsed) throw new Error("Code ou URL invalides.");
      const claimed = await claimPairing(parsed.host, parsed.code);
      await saveCredentials(claimed.token, claimed.base_url);
      router.replace("/onboarding/success");
    } catch (err) {
      Alert.alert("Appairage", err instanceof Error ? err.message : "Echec");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.label}>URL serveur</Text>
      <TextInput style={styles.input} value={host} onChangeText={setHost} autoCapitalize="none" />
      <Text style={styles.label}>Code 8 caracteres</Text>
      <TextInput style={styles.input} value={code} onChangeText={setCode} autoCapitalize="characters" maxLength={8} />
      <Pressable style={styles.btn} onPress={onSubmit} disabled={busy}>
        <Text style={styles.btnText}>{busy ? "Connexion..." : "Valider"}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate, padding: 20, gap: 10 },
  label: { color: colors.textMuted },
  input: {
    backgroundColor: colors.slateLight,
    color: colors.text,
    padding: 12,
    borderRadius: 8,
  },
  btn: {
    marginTop: 16,
    backgroundColor: colors.primary,
    padding: 14,
    borderRadius: 8,
    alignItems: "center",
  },
  btnText: { color: colors.white, fontWeight: "700" },
});
