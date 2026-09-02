import { apiGet, ApiConfig } from "./api";

/** Resume stats dashboard mobile. */
export interface MobileStats {
  calls_today: number;
  unread_voicemails: number;
}

/**
 * Recupere les stats publiques pour le dashboard mobile.
 *
 * @param config Configuration API Bearer.
 * @returns Nombre d appels du jour et messages non lus.
 */
export async function fetchMobileStats(config: ApiConfig): Promise<MobileStats> {
  const data = await apiGet<MobileStats>(config, "/public/stats");
  return {
    calls_today: Number(data.calls_today ?? 0),
    unread_voicemails: Number(data.unread_voicemails ?? 0),
  };
}
