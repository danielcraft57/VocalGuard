/**
 * Bootstrap WebSocket + notifications locales (LAN, pas de FCM cloud).
 */
import { Platform } from "react-native";
import type { Router } from "expo-router";
import { getStoredCredentials } from "./credentials";
import { log } from "./log";
import {
  notificationFromWsEvent,
  scheduleLocalNotification,
  setLocalNotificationScheduler,
} from "./localNotifications";
import { syncFromServer } from "./sync";
import { getAppDb } from "../db/getAppDb";
import { buildWsUrl, VocalGuardWsClient } from "./ws";

let wsClient: VocalGuardWsClient | null = null;
let notificationsReady = false;
let pendingPlayVoicemailId: number | null = null;

export type RealtimePlayRequest = (voicemailId: number) => void;

let onPlayVoicemail: RealtimePlayRequest | null = null;

/**
 * Enregistre le callback lecture message (ecran Messages).
 *
 * @param fn Callback declenche au tap notif ou event WS.
 */
export function setVoicemailPlayHandler(fn: RealtimePlayRequest | null): void {
  onPlayVoicemail = fn;
  if (pendingPlayVoicemailId != null && fn) {
    fn(pendingPlayVoicemailId);
    pendingPlayVoicemailId = null;
  }
}

/**
 * Demande lecture d un message (notif ou deep link).
 *
 * @param id Identifiant vocal.
 */
export function requestVoicemailPlay(id: number): void {
  if (onPlayVoicemail) {
    onPlayVoicemail(id);
    return;
  }
  pendingPlayVoicemailId = id;
}

/**
 * Configure expo-notifications (natif uniquement).
 */
async function ensureNotifications(): Promise<void> {
  if (notificationsReady || Platform.OS === "web") return;
  try {
    const Notifications = await import("expo-notifications");
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldPlaySound: true,
        shouldSetBadge: true,
        shouldShowBanner: true,
        shouldShowList: true,
      }),
    });
    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "VocalGuard",
        importance: Notifications.AndroidImportance.HIGH,
        sound: "default",
        vibrationPattern: [0, 250, 250, 250],
      });
    }
    const { status } = await Notifications.requestPermissionsAsync();
    if (status !== "granted") {
      log.warn("realtime", "permissions notifications refusees");
    }
    setLocalNotificationScheduler(async (payload) => {
      await Notifications.scheduleNotificationAsync({
        content: {
          title: payload.title,
          body: payload.body,
          data: payload.data ?? {},
          sound: "default",
        },
        trigger: null,
      });
    });
    notificationsReady = true;
  } catch (err) {
    log.warn("realtime", "expo-notifications indisponible", err);
  }
}

/**
 * Traite un evenement WS : notif + sync cache.
 *
 * @param type Type evenement backend.
 * @param payload Donnees.
 */
async function handleWsEvent(type: string, payload: Record<string, unknown>): Promise<void> {
  const notif = notificationFromWsEvent(type, payload);
  if (notif) {
    await scheduleLocalNotification(notif);
  }

  if (type === "voicemail.recorded" || type.startsWith("call.")) {
    try {
      const creds = await getStoredCredentials();
      if (!creds.baseUrl || !creds.token) return;
      const db = await getAppDb();
      const sync = await db.getFirstAsync<{ last_sync_at: string | null }>(
        "SELECT last_sync_at FROM sync_state WHERE id = 1",
      );
      await syncFromServer(db, { baseUrl: creds.baseUrl, token: creds.token }, sync?.last_sync_at ?? null);
    } catch (err) {
      log.warn("realtime", "sync apres event echouee", err);
    }
  }

  if (type === "voicemail.recorded" && payload.voicemail_id != null) {
    requestVoicemailPlay(Number(payload.voicemail_id));
  }
}

/**
 * Demarre le client WS si credentials presents.
 */
export async function startRealtime(): Promise<void> {
  await ensureNotifications();
  const creds = await getStoredCredentials();
  if (!creds.baseUrl || !creds.token) {
    log.debug("realtime", "pas de credentials, WS ignore");
    return;
  }
  if (wsClient) {
    wsClient.disconnect();
    wsClient = null;
  }
  const url = buildWsUrl(creds.baseUrl, creds.token);
  log.info("realtime", "connexion WS");
  wsClient = new VocalGuardWsClient(
    url,
    (evt) => {
      void handleWsEvent(evt.type, evt.payload);
    },
    (connected) => {
      log.info("realtime", connected ? "WS connecte" : "WS deconnecte");
    },
  );
  wsClient.connect();
}

/**
 * Arrete le client WS.
 */
export function stopRealtime(): void {
  wsClient?.disconnect();
  wsClient = null;
}

/**
 * Branche l ecoute des taps sur notifications (navigation + lecture).
 *
 * @param router Router Expo.
 */
export function bindNotificationResponses(router: Router): () => void {
  if (Platform.OS === "web") {
    return () => undefined;
  }
  let sub: { remove: () => void } | null = null;
  void (async () => {
    try {
      const Notifications = await import("expo-notifications");
      sub = Notifications.addNotificationResponseReceivedListener((response) => {
        const data = response.notification.request.content.data as Record<string, string | undefined>;
        const type = data.type ?? "";
        if (type === "voicemail.recorded" && data.voicemail_id) {
          router.push("/(tabs)/messages");
          requestVoicemailPlay(Number(data.voicemail_id));
          return;
        }
        if (type === "call.incoming" || type === "call.missed") {
          router.push("/(tabs)/calls");
        }
      });
    } catch (err) {
      log.warn("realtime", "bindNotificationResponses failed", err);
    }
  })();
  return () => sub?.remove();
}
