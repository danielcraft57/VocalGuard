/**
 * Redirection onboarding / tabs (sans dependre d Expo Router).
 */

export type AuthRedirect = "/onboarding" | "/(tabs)/calls";

/**
 * Decide ou envoyer l utilisateur selon token et premier segment de route.
 *
 * @param token Token API ou null.
 * @param firstSegment Premier segment Expo Router (ex. onboarding, (tabs)).
 * @returns Cible, ou null si on reste.
 * @example
 * resolveAuthRedirect(null, undefined); // "/onboarding"
 * resolveAuthRedirect("abc", "onboarding"); // "/(tabs)/calls"
 */
export function resolveAuthRedirect(
  token: string | null,
  firstSegment: string | undefined,
  secondSegment?: string | undefined,
): AuthRedirect | null {
  const inOnboarding = firstSegment === "onboarding";
  const pairingScreen =
    secondSegment === "success" || secondSegment === "scan" || secondSegment === "manual";

  if (!token && !inOnboarding) return "/onboarding";
  if (token && inOnboarding && !pairingScreen) return "/(tabs)/calls";
  if (token && (!firstSegment || firstSegment === "index")) return "/(tabs)/calls";
  return null;
}
