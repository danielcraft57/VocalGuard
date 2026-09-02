import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Alert } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { getStoredCredentials } from "../../src/services/credentials";
import { DialPad } from "../../src/components/DialPad";
import { apiPost } from "../../src/services/api";
import { pingHealth } from "../../src/services/connectivity";
import { resolveOutgoingState } from "../../src/services/outgoingAudio";
import { routeParam } from "../../src/utils/nav";
import { colors } from "../../src/theme/colors";
import { icons } from "../../src/theme/icons";
import { MaterialCommunityIcons } from "@expo/vector-icons";

/**
 * Composer / dialer (online LAN uniquement).
 */
export default function DialerScreen() {
  const params = useLocalSearchParams<{ phone?: string }>();
  const [phone, setPhone] = useState("");
  const [online, setOnline] = useState(false);

  useEffect(() => {
    const incoming = routeParam(params.phone);
    if (incoming) setPhone(incoming);
  }, [params.phone]);

  useEffect(() => {
    void (async () => {
      const { baseUrl } = await getStoredCredentials();
      setOnline(await pingHealth(baseUrl ?? ""));
    })();
  }, []);

  const state = resolveOutgoingState(online);
  const disabled = state === "offline";

  const onCall = async () => {
    const { baseUrl, token } = await getStoredCredentials();
    if (!baseUrl || !token) {
      Alert.alert("Configuration", "Appairage requis.");
      return;
    }
    try {
      const res = await apiPost<{ call_id: number; message: string }>(
        { baseUrl, token },
        "/public/calls/outgoing/start",
        { phone_number: phone },
      );
      Alert.alert("Appel sortant", res.message ?? `Session #${res.call_id}`);
    } catch (err) {
      Alert.alert("Erreur", err instanceof Error ? err.message : "Echec appel sortant");
    }
  };

  return (
    <View style={styles.container}>
      {disabled ? (
        <View style={styles.offline}>
          <MaterialCommunityIcons name={icons.wifiAlert} size={28} color={colors.danger} />
          <Text style={styles.offlineText}>Serveur injoignable - verifie le Wi-Fi ou le VPN</Text>
        </View>
      ) : null}
      <DialPad phone={phone} onChange={setPhone} onCall={onCall} disabled={disabled} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate },
  offline: { flexDirection: "row", alignItems: "center", gap: 8, padding: 12, backgroundColor: colors.slateLight },
  offlineText: { color: colors.text, flex: 1 },
});
