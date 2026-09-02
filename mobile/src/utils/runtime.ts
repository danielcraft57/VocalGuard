import Constants from "expo-constants";
import { Platform } from "react-native";

/**
 * True si l app tourne dans Expo Go (pas un dev build / prod).
 */
export function isExpoGo(): boolean {
  return Constants.executionEnvironment === "storeClient";
}

/**
 * True si les notifications locales natives sont disponibles (pas le web).
 * Push distant : necessite un dev build, pas Expo Go SDK 53+.
 */
export function canUseExpoNotifications(): boolean {
  if (Platform.OS === "web") return false;
  return true;
}
