import React, { useCallback, useRef, useState } from "react";
import { View, Text, Pressable, StyleSheet, ActivityIndicator } from "react-native";
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from "expo-camera";
import { Link, useRouter } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { claimPairing } from "../../src/services/api";
import { parsePairUri } from "../../src/services/pairing";
import { saveCredentials } from "../_layout";
import { colors } from "../../src/theme/colors";
import { icons } from "../../src/theme/icons";

/**
 * Ecran scan QR : camera + cadre, claim token, puis ecran victoire.
 */
export default function ScanPairingScreen() {
  const router = useRouter();
  const [permission, requestPermission] = useCameraPermissions();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const handledRef = useRef(false);

  const handleBarcode = useCallback(
    async (result: BarcodeScanningResult) => {
      if (handledRef.current || busy) return;
      const raw = (result.data || "").trim();
      if (!raw) return;

      const parsed = parsePairUri(raw);
      if (!parsed) {
        setError("QR non reconnu. Attendu: vocalguard://pair?...");
        return;
      }

      handledRef.current = true;
      setBusy(true);
      setError(null);
      try {
        const claimed = await claimPairing(parsed.host, parsed.code);
        await saveCredentials(claimed.token, claimed.base_url);
        router.replace("/onboarding/success");
      } catch (err) {
        handledRef.current = false;
        setError(err instanceof Error ? err.message : "Appairage echoue.");
        setBusy(false);
      }
    },
    [busy, router],
  );

  if (!permission) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <MaterialCommunityIcons name={icons.qrScan} size={48} color={colors.primary} />
        <Text style={styles.title}>Autoriser la camera</Text>
        <Text style={styles.hint}>Necessaire pour scanner le QR depuis la page web App mobile.</Text>
        <Pressable style={styles.primary} onPress={requestPermission}>
          <Text style={styles.primaryText}>Autoriser</Text>
        </Pressable>
        <Link href="/onboarding/manual" asChild>
          <Pressable style={styles.secondary}>
            <Text style={styles.secondaryText}>Saisie manuelle du code</Text>
          </Pressable>
        </Link>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
        onBarcodeScanned={busy ? undefined : handleBarcode}
      />
      <View style={styles.overlay}>
        <Text style={styles.overlayTitle}>Cadre le QR VocalGuard</Text>
        <View style={styles.frame} />
        {busy ? <ActivityIndicator color={colors.primary} style={styles.spinner} /> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <Link href="/onboarding/manual" asChild>
          <Pressable style={styles.secondary}>
            <Text style={styles.secondaryText}>Saisie manuelle</Text>
          </Pressable>
        </Link>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },
  center: {
    flex: 1,
    backgroundColor: colors.slate,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 12,
  },
  title: { color: colors.text, fontSize: 20, fontWeight: "700", textAlign: "center" },
  hint: { color: colors.textMuted, textAlign: "center" },
  overlay: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "rgba(15, 23, 42, 0.35)",
    padding: 24,
  },
  overlayTitle: {
    color: colors.white,
    fontSize: 18,
    fontWeight: "600",
    marginBottom: 24,
  },
  frame: {
    width: 240,
    height: 240,
    borderWidth: 3,
    borderColor: colors.primary,
    borderRadius: 16,
    backgroundColor: "transparent",
  },
  spinner: { marginTop: 20 },
  error: {
    marginTop: 16,
    color: colors.danger,
    textAlign: "center",
    backgroundColor: "rgba(0,0,0,0.55)",
    padding: 10,
    borderRadius: 8,
  },
  primary: {
    backgroundColor: colors.primary,
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 10,
    marginTop: 8,
  },
  primaryText: { color: colors.white, fontWeight: "700" },
  secondary: { padding: 14, marginTop: 12 },
  secondaryText: { color: colors.neutral200, textAlign: "center" },
});
