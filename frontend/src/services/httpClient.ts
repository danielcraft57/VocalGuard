/**
 * Retourne l'URL de base de l'API VocalGuard.
 *
 * - Cote navigateur : on utilise un chemin relatif /api/v1 pour que les appels
 *   soient same-origin quand le front est servi par le backend (pas de CORS, vraies donnees).
 * - Cote build (Node) : on utilise la variable d'env ou localhost pour le fallback.
 *
 * @returns URL de base de l'API.
 */
export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    return (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").trim() || "/api/v1";
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
}

/**
 * Helper minimal pour effectuer une requete GET et parser du JSON.
 *
 * @param path Chemin relatif a l'API (ex: /calls).
 * @returns Donnees parsees typées.
 */
export async function getJson<T>(path: string): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}${path}`, { cache: "no-store" });

  if (!res.ok) {
    throw new Error(`Erreur API GET ${path}: ${res.status}`);
  }

  return (await res.json()) as T;
}

