/**
 * Bootstrap WebSocket + notifications locales (LAN, pas de FCM cloud).
 */
import { AppState, type NativeEventSubscription } from "react-native";
import type { Router } from "expo-router";
import type { VoicemailRow } from "../db/schema";
import { getStoredCredentials } from "./credentials";
import { log } from "./log";
import { canUseExpoNotifications } from "../utils/runtime";
import {
  notificationFromWsEvent,
  scheduleLocalNotification,
  setLocalNotificationScheduler,
} from "./localNotifications";
import {
  addNotificationResponseReceivedListener,
  presentExpoLocalNotification,
  setupExpoLocalNotifications,
} from "./expoNotificationsLocal";
import { syncFromServer } from "./sync";
import { getAppDb } from "../db/getAppDb";
import { buildWsUrl, VocalGuardWsClient } from "./ws";

let wsClient: VocalGuardWsClient | null = null;
let notificationsReady = false;
let pendingPlayVoicemailId: number | null = null;
let appStateSub: NativeEventSubscription | null = null;
const MISSED_VM_WINDOW_MS = 5 * 60 * 1000;

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
 * Configure les notifications locales (sans module push Expo Go).
 */
async function ensureNotifications(): Promise<void> {
  if (notificationsReady || !canUseExpoNotifications()) return;
  try {
    const granted = await setupExpoLocalNotifications();
    if (!granted) {
      log.warn("realtime", "permissions notifications refusees");
    }
    setLocalNotificationScheduler(async (payload) => {
      await presentExpoLocalNotification(payload);
    });
    notificationsReady = true;
  } catch (err) {
    log.warn("realtime", "notifications locales indisponibles", err);
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

  if (type === "voicemail.recorded" || type === "voicemail.transcribed" || type.startsWith("call.")) {
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
}

/**
 * Ouvre ou rouvre le client WebSocket.
 */
async function connectWsClient(): Promise<void> {
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
  log.info("realtime", "connexion WS", { url: url.replace(/token=[^&]+/, "token=***") });
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
 * Sync apres retour au premier plan : rattrape les notifs manquees (WS coupe en arriere-plan).
 */
async function catchUpAfterForeground(): Promise<void> {
  try {
    const creds = await getStoredCredentials();
    if (!creds.baseUrl || !creds.token) return;
    const db = await getAppDb();
    const known = new Set(
      (await db.getAllAsync<{ id: number }>("SELECT id FROM voicemails")).map((r) => r.id),
    );
    const sync = await db.getFirstAsync<{ last_sync_at: string | null }>(
      "SELECT last_sync_at FROM sync_state WHERE id = 1",
    );
    await syncFromServer(db, { baseUrl: creds.baseUrl, token: creds.token }, sync?.last_sync_at ?? null);
    const fresh = await db.getAllAsync<VoicemailRow>(
      "SELECT * FROM voicemails ORDER BY recorded_at DESC LIMIT 20",
    );
    const cutoff = Date.now() - MISSED_VM_WINDOW_MS;
    for (const row of fresh) {
      if (known.has(row.id)) continue;
      const at = row.recorded_at ? Date.parse(row.recorded_at) : 0;
      if (!at || at < cutoff) continue;
      const phone = row.caller_name ?? row.caller_number;
      await scheduleLocalNotification({
        title: "Nouveau message vocal",
        body: `Message de ${phone}`,
        data: { type: "voicemail.recorded", voicemail_id: String(row.id) },
      });
    }
  } catch (err) {
    log.warn("realtime", "catch-up foreground echoue", err);
  }
}

/**
 * Demarre le client WS si credentials presents.
 */
export async function startRealtime(): Promise<void> {
  await ensureNotifications();
  await connectWsClient();
  if (!appStateSub) {
    appStateSub = AppState.addEventListener("change", (state) => {
      if (state !== "active") return;
      void connectWsClient();
      void catchUpAfterForeground();
    });
  }
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
  if (!canUseExpoNotifications()) {
    return () => undefined;
  }
  let sub: { remove: () => void } | null = null;
  void (async () => {
    try {
      await setupExpoLocalNotifications();
      sub = addNotificationResponseReceivedListener((response) => {
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
