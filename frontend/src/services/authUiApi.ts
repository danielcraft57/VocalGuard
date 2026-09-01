import { getApiBaseUrl } from "./httpClient";

/** Etat session UI web. */
export interface UiSessionStatus {
  authenticated: boolean;
  ui_password_enabled: boolean;
}

/**
 * Effectue une requete API interne avec cookie de session.
 *
 * @param path Chemin relatif sous /api/v1.
 * @param init Options fetch supplementaires.
 * @returns Reponse HTTP brute.
 */
async function uiFetch(path: string, init?: RequestInit): Promise<Response> {
  const baseUrl = getApiBaseUrl();
  return fetch(`${baseUrl}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
}

/**
 * Recupere l etat de session UI (mot de passe active ou non).
 *
 * @returns Statut d authentification.
 */
export async function fetchUiSession(): Promise<UiSessionStatus> {
  const res = await uiFetch("/auth/ui/me", { method: "GET", cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Impossible de verifier la session UI (${res.status}).`);
  }
  return (await res.json()) as UiSessionStatus;
}

/**
 * Authentifie l utilisateur avec le mot de passe UI partage.
 *
 * @param password Mot de passe saisi.
 * @throws Erreur si identifiants invalides.
 */
export async function loginUi(password: string): Promise<void> {
  const res = await uiFetch("/auth/ui/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    const detail = res.status === 401 ? "Mot de passe incorrect." : `Connexion impossible (${res.status}).`;
    throw new Error(detail);
  }
}

/**
 * Deconnecte la session UI (efface le cookie httpOnly).
 */
export async function logoutUi(): Promise<void> {
  await uiFetch("/auth/ui/logout", { method: "POST" });
}
