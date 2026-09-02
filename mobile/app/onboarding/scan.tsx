import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, Pressable, StyleSheet, ActivityIndicator } from "react-native";
import { useIsFocused, useFocusEffect } from "@react-navigation/native";
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from "expo-camera";
import { Link, useRouter } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { claimPairing } from "../../src/services/api";
import { barcodeScanPayload, parsePairUri } from "../../src/services/pairing";
import { log } from "../../src/services/log";
import { saveCredentials } from "../_layout";
import { colors } from "../../src/theme/colors";
import { icons } from "../../src/theme/icons";

/**
 * Ecran scan QR : camera + cadre, claim token, puis ecran victoire.
 */
export default function ScanPairingScreen() {
  const router = useRouter();
  const isFocused = useIsFocused();
  const [permission, requestPermission] = useCameraPermissions();
  const [busy, setBusy] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const modernScannerAvailable = CameraView.isModernBarcodeScannerAvailable;

  useFocusEffect(
    useCallback(() => {
      busyRef.current = false;
      setBusy(false);
      setError(null);
      setCameraReady(false);
    }, []),
  );

  const processScan = useCallback(
    async (raw: string) => {
      if (busyRef.current) return;
      const text = raw.trim();
      if (!text) return;

      log.info("pairing", "scan detecte", { len: text.length });

      const parsed = parsePairUri(text);
      if (!parsed) {
        setError("QR non reconnu. Attendu: vocalguard://pair?...");
        return;
      }

      busyRef.current = true;
      setBusy(true);
      setError(null);
      try {
        const claimed = await claimPairing(parsed.host, parsed.code);
        await saveCredentials(claimed.token, claimed.base_url);
        router.replace("/onboarding/success");
      } catch (err) {
        busyRef.current = false;
        setError(err instanceof Error ? err.message : "Appairage echoue.");
        setBusy(false);
      }
    },
    [router],
  );

  const onBarcodeScanned = useCallback(
    (result: BarcodeScanningResult) => {
      void processScan(barcodeScanPayload(result));
    },
    [processScan],
  );

  useEffect(() => {
    if (!permission?.granted) return;
    const sub = CameraView.onModernBarcodeScanned((event) => {
      void processScan(event.data ?? "");
    });
    return () => sub.remove();
  }, [permission?.granted, processScan]);

  const openModernScanner = useCallback(async () => {
    if (!modernScannerAvailable || busyRef.current) return;
    try {
      await CameraView.launchScanner({ barcodeTypes: ["qr"] });
    } catch (err) {
      log.warn("pairing", "modern scanner failed", err);
      setError("Scanner systeme indisponible.");
    }
  }, [modernScannerAvailable]);

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

  const scanningEnabled = isFocused && cameraReady && !busy;

  return (
    <View style={styles.container}>
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        active={isFocused && !busy}
        autofocus="on"
        barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
        onCameraReady={() => setCameraReady(true)}
        onMountError={(event) => setError(event.message)}
        onBarcodeScanned={scanningEnabled ? onBarcodeScanned : undefined}
      />
      <View style={styles.overlay} pointerEvents="box-none">
        <Text style={styles.overlayTitle}>Cadre le QR VocalGuard</Text>
        <View style={styles.frame} />
        {!cameraReady ? (
          <Text style={styles.hintOverlay}>Initialisation camera...</Text>
        ) : (
          <Text style={styles.hintOverlay}>Detection automatique activee</Text>
        )}
        {busy ? <ActivityIndicator color={colors.primary} style={styles.spinner} /> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}
        {modernScannerAvailable ? (
          <Pressable style={styles.modernBtn} onPress={() => void openModernScanner()} disabled={busy}>
            <MaterialCommunityIcons name={icons.qrScan} size={20} color={colors.slate} />
            <Text style={styles.modernBtnText}>Scanner systeme (plus fiable)</Text>
          </Pressable>
        ) : null}
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
    ...StyleSheet.absoluteFillObject,
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
    width: 260,
    height: 260,
    borderWidth: 3,
    borderColor: colors.primary,
    borderRadius: 16,
    backgroundColor: "transparent",
  },
  hintOverlay: { color: colors.neutral200, marginTop: 16, fontSize: 13 },
  spinner: { marginTop: 20 },
  error: {
    marginTop: 16,
    color: colors.danger,
    textAlign: "center",
    backgroundColor: "rgba(0,0,0,0.55)",
    padding: 10,
    borderRadius: 8,
  },
  modernBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.primary,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 999,
    marginTop: 16,
  },
  modernBtnText: { color: colors.slate, fontWeight: "700" },
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
