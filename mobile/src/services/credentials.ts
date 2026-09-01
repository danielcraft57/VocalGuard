/**
 * Stockage credentials mobile : SecureStore (natif) ou localStorage (web dev).
 */
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import { log } from "./log";

export const TOKEN_KEY = "vg_mobile_api_token";
export const BASE_KEY = "vg_mobile_base_url";

const WEB_PREFIX = "vg:";

/**
 * Indique si on utilise le fallback web (localStorage).
 */
function useWebStorage(): boolean {
  return Platform.OS === "web";
}

/**
 * Lit une valeur stockee.
 *
 * @param key Cle.
 * @returns Valeur ou null.
 */
async function getItem(key: string): Promise<string | null> {
  if (useWebStorage()) {
    try {
      if (typeof localStorage === "undefined") return null;
      return localStorage.getItem(`${WEB_PREFIX}${key}`);
    } catch (err) {
      log.warn("credentials", "localStorage get failed", err);
      return null;
    }
  }
  return SecureStore.getItemAsync(key);
}

/**
 * Ecrit une valeur stockee.
 *
 * @param key Cle.
 * @param value Valeur.
 */
async function setItem(key: string, value: string): Promise<void> {
  if (useWebStorage()) {
    if (typeof localStorage === "undefined") {
      throw new Error("localStorage indisponible sur ce navigateur.");
    }
    localStorage.setItem(`${WEB_PREFIX}${key}`, value);
    log.debug("credentials", "localStorage set", { key });
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

/**
 * Supprime une valeur stockee.
 *
 * @param key Cle.
 */
async function removeItem(key: string): Promise<void> {
  if (useWebStorage()) {
    if (typeof localStorage !== "undefined") {
      localStorage.removeItem(`${WEB_PREFIX}${key}`);
    }
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

/**
 * Lit le token et l URL serveur.
 *
 * @returns Credentials ou null.
 */
export async function getStoredCredentials(): Promise<{ token: string | null; baseUrl: string | null }> {
  const [token, baseUrl] = await Promise.all([getItem(TOKEN_KEY), getItem(BASE_KEY)]);
  log.debug("credentials", "read", {
    backend: useWebStorage() ? "web" : "secure",
    hasToken: Boolean(token),
    hasBaseUrl: Boolean(baseUrl),
  });
  return { token, baseUrl };
}

/**
 * Persiste les credentials apres appairage QR.
 *
 * @param token Token API Bearer.
 * @param baseUrl URL racine serveur.
 */
export async function saveCredentials(token: string, baseUrl: string): Promise<void> {
  await setItem(TOKEN_KEY, token);
  await setItem(BASE_KEY, baseUrl);
  log.info("credentials", "saved", { baseUrl });
}

/**
 * Efface les credentials (deconnexion / re-appairage).
 */
export async function clearCredentials(): Promise<void> {
  await removeItem(TOKEN_KEY);
  await removeItem(BASE_KEY);
  log.info("credentials", "cleared");
}
