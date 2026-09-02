/**
 * Wrapper expo-notifications : imports cibles sans le barrel index.
 * Evite le side-effect push (DevicePushTokenAutoRegistration) qui declenche
 * l'erreur Expo Go SDK 53+ alors qu'on n'utilise que des notifs locales.
 */
import { Platform } from "react-native";
import scheduleNotificationAsync from "expo-notifications/build/scheduleNotificationAsync";
import { setNotificationHandler } from "expo-notifications/build/NotificationsHandler";
import { requestPermissionsAsync } from "expo-notifications/build/NotificationPermissions";
import setNotificationChannelAsync from "expo-notifications/build/setNotificationChannelAsync";
import { addNotificationResponseReceivedListener } from "expo-notifications/build/NotificationsEmitter";
import { AndroidImportance } from "expo-notifications/build/NotificationChannelManager.types";
import type { LocalNotificationPayload } from "./localNotifications";

let ready = false;

/**
 * Configure handler, canal Android et permissions (notifs locales uniquement).
 */
export async function setupExpoLocalNotifications(): Promise<boolean> {
  if (ready) return true;
  if (Platform.OS === "web") return false;

  setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: true,
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });

  if (Platform.OS === "android") {
    await setNotificationChannelAsync("default", {
      name: "VocalGuard",
      importance: AndroidImportance.HIGH,
      sound: "default",
      vibrationPattern: [0, 250, 250, 250],
    });
  }

  const { status } = await requestPermissionsAsync();
  ready = status === "granted";
  return ready;
}

/**
 * Affiche une notification locale immediate.
 *
 * @param payload Titre, corps et donnees navigation.
 */
export async function presentExpoLocalNotification(payload: LocalNotificationPayload): Promise<void> {
  await setupExpoLocalNotifications();
  await scheduleNotificationAsync({
    content: {
      title: payload.title,
      body: payload.body,
      data: payload.data ?? {},
      sound: "default",
      ...(Platform.OS === "android" ? { channelId: "default" } : {}),
    },
    trigger: null,
  });
}

export { addNotificationResponseReceivedListener };
