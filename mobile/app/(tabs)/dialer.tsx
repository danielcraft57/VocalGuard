import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Alert, Pressable, Platform } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { getStoredCredentials } from "../../src/services/credentials";
import { DialPad } from "../../src/components/DialPad";
import { pingHealth } from "../../src/services/connectivity";
import { resolveOutgoingState } from "../../src/services/outgoingAudio";
import {
  deriveTelephonyWsBaseFromApi,
  hangupOutgoingCall,
  pingMobileTelephony,
  sendOutgoingDtmf,
  startOutgoingCall,
} from "../../src/services/outgoingCall";
import { LiveOutgoingAudioSession } from "../../src/services/liveOutgoingAudio";
import { routeParam } from "../../src/utils/nav";
import { colors } from "../../src/theme/colors";
import { icons } from "../../src/theme/icons";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import type { ApiConfig } from "../../src/services/api";

type CallPhase = "idle" | "dialing" | "connected" | "ended" | "error";

/**
 * Composer / dialer : API publique -> daemon -> modem ou VoIP.
 */
export default function DialerScreen() {
  const params = useLocalSearchParams<{ phone?: string }>();
  const [phone, setPhone] = useState("");
  const [online, setOnline] = useState(false);
  const [phase, setPhase] = useState<CallPhase>("idle");
  const [callId, setCallId] = useState<number | null>(null);
  const [statusLine, setStatusLine] = useState("");
  const [audioHint, setAudioHint] = useState("");
  const audioRef = useRef<LiveOutgoingAudioSession | null>(null);
  const cfgRef = useRef<ApiConfig | null>(null);

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

  const cleanupAudio = useCallback(() => {
    audioRef.current?.stop();
    audioRef.current = null;
  }, []);

  useEffect(() => {
    return () => {
      cleanupAudio();
    };
  }, [cleanupAudio]);

  const state = resolveOutgoingState(online);
  const disabled = state === "offline" || phase === "dialing" || phase === "connected";

  const onHangup = async () => {
    const cfg = cfgRef.current;
    const id = callId;
    cleanupAudio();
    if (cfg && id != null) {
      await hangupOutgoingCall(cfg, id);
    }
    setPhase("ended");
    setStatusLine("Raccroche");
    setTimeout(() => {
      setPhase("idle");
      setCallId(null);
      setStatusLine("");
      setAudioHint("");
    }, 800);
  };

  const onDtmf = async (digit: string) => {
    const cfg = cfgRef.current;
    const id = callId;
    if (!cfg || id == null || phase !== "connected") return;
    await sendOutgoingDtmf(cfg, id, digit);
  };

  const onCall = async () => {
    const { baseUrl, token } = await getStoredCredentials();
    if (!baseUrl || !token) {
      Alert.alert("Configuration", "Appairage requis.");
      return;
    }
    const cfg: ApiConfig = { baseUrl, token };
    cfgRef.current = cfg;
    setPhase("dialing");
    setStatusLine("Composition...");
    setAudioHint("");
    try {
      let telephonyBase = deriveTelephonyWsBaseFromApi(baseUrl);
      try {
        const ping = await pingMobileTelephony(cfg);
        if (ping.telephony_ws_base) {
          telephonyBase = ping.telephony_ws_base.includes("/ws/outgoing-call")
            ? ping.telephony_ws_base
            : `${ping.telephony_ws_base.replace(/\/$/, "")}/ws/outgoing-call`;
        }
        if (ping.telephony_backend) {
          setStatusLine(`Composition (${ping.telephony_backend})...`);
        }
      } catch {
        /* ping optionnel */
      }

      const res = await startOutgoingCall(cfg, phone.trim());
      setCallId(res.call_id);
      setPhase("connected");
      setStatusLine(res.message ?? `Appel #${res.call_id}`);

      const session = new LiveOutgoingAudioSession(telephonyBase, res.call_id, {
        onStatus: (s) => {
          if (s === "open") {
            setAudioHint(
              Platform.OS === "web"
                ? "Audio live (micro + HP)"
                : "Audio ligne (HP) - micro full-duplex sur Expo web",
            );
          }
          if (s === "error") setAudioHint("Audio WS en erreur");
        },
        onRemoteAudio: () => {
          setPhase((p) => (p === "dialing" ? "connected" : p));
        },
      });
      audioRef.current = session;
      session.start();
    } catch (err) {
      cleanupAudio();
      setPhase("error");
      setStatusLine(err instanceof Error ? err.message : "Echec appel");
      Alert.alert("Erreur", err instanceof Error ? err.message : "Echec appel sortant");
      setTimeout(() => {
        setPhase("idle");
        setStatusLine("");
      }, 1200);
    }
  };

  if (phase === "dialing" || phase === "connected") {
    return (
      <View style={styles.container}>
        <View style={styles.inCall}>
          <MaterialCommunityIcons name={icons.outgoing} size={48} color={colors.primary} />
          <Text style={styles.inCallNumber}>{phone}</Text>
          <Text style={styles.inCallStatus}>{statusLine}</Text>
          {audioHint ? <Text style={styles.audioHint}>{audioHint}</Text> : null}
          <View style={styles.dtmfRow}>
            {["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"].map((d) => (
              <Pressable
                key={d}
                style={styles.dtmfKey}
                onPress={() => void onDtmf(d)}
                disabled={phase !== "connected"}
              >
                <Text style={styles.dtmfText}>{d}</Text>
              </Pressable>
            ))}
          </View>
          <Pressable style={styles.hangupBtn} onPress={() => void onHangup()}>
            <Text style={styles.hangupText}>Raccrocher</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {disabled && phase === "idle" && state === "offline" ? (
        <View style={styles.offline}>
          <MaterialCommunityIcons name={icons.wifiAlert} size={28} color={colors.danger} />
          <Text style={styles.offlineText}>Serveur injoignable - verifie le Wi-Fi ou le VPN</Text>
        </View>
      ) : null}
      {statusLine && phase === "error" ? (
        <Text style={styles.errorLine}>{statusLine}</Text>
      ) : null}
      <DialPad
        phone={phone}
        onChange={setPhone}
        onCall={() => void onCall()}
        disabled={state === "offline"}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.slate },
  offline: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    padding: 12,
    backgroundColor: colors.slateLight,
  },
  offlineText: { color: colors.text, flex: 1 },
  errorLine: { color: colors.danger, padding: 12, textAlign: "center" },
  inCall: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 12 },
  inCallNumber: { color: colors.white, fontSize: 28, fontWeight: "600" },
  inCallStatus: { color: colors.textMuted, fontSize: 16 },
  audioHint: { color: colors.text, fontSize: 13, textAlign: "center", marginBottom: 8 },
  dtmfRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "center",
    gap: 10,
    maxWidth: 280,
    marginVertical: 16,
  },
  dtmfKey: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.slateLight,
    alignItems: "center",
    justifyContent: "center",
  },
  dtmfText: { color: colors.white, fontSize: 20, fontWeight: "600" },
  hangupBtn: {
    backgroundColor: colors.danger,
    paddingHorizontal: 40,
    paddingVertical: 16,
    borderRadius: 999,
    marginTop: 12,
  },
  hangupText: { color: colors.white, fontSize: 18, fontWeight: "700" },
});
