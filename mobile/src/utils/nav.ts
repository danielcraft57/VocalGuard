import type { Router } from "expo-router";

/**
 * Normalise un param route Expo (string | string[] | undefined).
 */
export function routeParam(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

/**
 * Ouvre l onglet composeur avec un numero pre-rempli.
 */
export function navigateToDialer(router: Router, phone: string): void {
  const trimmed = phone.trim();
  if (!trimmed) return;
  router.navigate({
    pathname: "/(tabs)/dialer",
    params: { phone: trimmed },
  });
}
