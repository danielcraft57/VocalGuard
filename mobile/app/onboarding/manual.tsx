import React, { useState } from "react";
import { View, Text, TextInput, Pressable, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { claimPairing, pingMobile } from "../../src/services/api";
import { parsePairUri } from "../../src/services/pairing";
import { saveCredentials } from "../_layout";
import { colors } from "../../src/theme/colors";

/**
 * Detecte un token API public (cle longue) vs un code appairage 8 chars.
 *
 * @param value Saisie utilisateur.
 * @returns "code" | "token" | "invalid".
 */
function detectCredentialKind(value: string): "code" | "token" | "invalid" {
  const v = value.trim();
  if (/^[A-Za-z0-9]{8}$/.test(v)) return "code";
  if (v.length >= 24) return "token";
  return "invalid";
}

/**
 * Fallback saisie URL + code 8 caracteres, ou token API direct (dev web).
 * Affiche les erreurs inline (Alert ne marche pas sur web).
 */
export default function ManualPairingScreen() {
  const router = useRouter();
  const [host, setHost] = useState("https://vocalguard.danielcraft.fr");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async () => {
    setBusy(true);
    setError(null);
    try {
      const baseUrl = host.replace(/\/$/, "").trim();
      if (!baseUrl.startsWith("http://") && !baseUrl.startsWith("https://")) {
        throw new Error("URL invalide (doit commencer par http:// ou https://).");
      }

      const kind = detectCredentialKind(secret);
      if (kind === "invalid") {
        throw new Error(
          "Saisis le code a 8 caracteres (page App mobile), ou colle un token API complet (bouton Voir).",
        );
      }

      if (kind === "token") {
        const token = secret.trim();
        await pingMobile({ baseUrl, token });
        await saveCredentials(token, baseUrl);
        router.replace("/onboarding/success");
        return;
      }

      const encodedHost = encodeURIComponent(baseUrl);
      const parsed = parsePairUri(`vocalguard://pair?v=1&host=${encodedHost}&code=${secret.trim()}`);
      if (!parsed) throw new Error("Code ou URL invalides.");
      const claimed = await claimPairing(parsed.host, parsed.code);
      await saveCredentials(claimed.token, claimed.base_url);
      router.replace("/onboarding/success");
    } catch (err) {
      const raw = err instanceof Error ? err.message : "Echec de l'appairage.";
      let message = raw.replace(/^Claim echoue:\s*/i, "").trim() || raw;
      if (/API GET .* -> 401/i.test(message) || /401/.test(message)) {
        message = "Token refuse (401). Verifie qu il est actif et a les droits mobile (Appels, Messages).";
      }
      setError(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.help}>
        Preferable : page web <Text style={styles.helpBold}>App mobile</Text> puis Generer un QR
        (code 8 caracteres, 20 min).{"\n"}
        Alternative : page <Text style={styles.helpBold}>API publique</Text>, bouton Voir, coller
        le token entier ici.
      </Text>

      <Text style={styles.label}>URL serveur</Text>
      <TextInput
        style={styles.input}
        value={host}
        onChangeText={(v) => {
          setHost(v);
          setError(null);
        }}
        autoCapitalize="none"
        autoCorrect={false}
      />

      <Text style={styles.label}>Code 8 caracteres OU token API</Text>
      <TextInput
        style={[styles.input, styles.secretInput]}
        value={secret}
        onChangeText={(v) => {
          setSecret(v);
          setError(null);
        }}
        autoCapitalize="characters"
        autoCorrect={false}
        placeholder="Ex. A1B2C3D4 ou 034075e492..."
        placeholderTextColor={colors.textMuted}
      />

      {error ? (
        <View style={styles.errorBox} accessibilityRole="alert">
          <Text style={styles.errorTitle}>Appairage impossible</Text>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      <Pressable style={[styles.btn, busy && styles.btnDisabled]} onPress={onSubmit} disabled={busy}>
        <Text style={styles.btnText}>{busy ? "Connexion..." : "Valider"}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate, padding: 20, gap: 10 },
  help: { color: colors.textMuted, fontSize: 13, lineHeight: 20, marginBottom: 8 },
  helpBold: { color: colors.neutral200, fontWeight: "700" },
  label: { color: colors.textMuted },
  input: {
    backgroundColor: colors.slateLight,
    color: colors.text,
    padding: 12,
    borderRadius: 8,
  },
  secretInput: { fontFamily: "monospace", letterSpacing: 0.5 },
  errorBox: {
    marginTop: 8,
    padding: 12,
    borderRadius: 8,
    backgroundColor: "rgba(239, 68, 68, 0.12)",
    borderWidth: 1,
    borderColor: "rgba(239, 68, 68, 0.35)",
    gap: 4,
  },
  errorTitle: { color: colors.danger, fontWeight: "700", fontSize: 14 },
  errorText: { color: colors.neutral200, fontSize: 14, lineHeight: 20 },
  btn: {
    marginTop: 16,
    backgroundColor: colors.primary,
    padding: 14,
    borderRadius: 8,
    alignItems: "center",
  },
  btnDisabled: { opacity: 0.6 },
  btnText: { color: colors.white, fontWeight: "700" },
});
