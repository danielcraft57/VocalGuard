/**
 * Retourne l'URL de base de l'API VocalGuard.
 *
 * On lit d'abord la variable d'environnement NEXT_PUBLIC_API_BASE_URL,
 * puis on retombe sur http://localhost:8000/api/v1 en dev.
 *
 * @returns URL de base de l'API.
 */
export function getApiBaseUrl(): string {
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

