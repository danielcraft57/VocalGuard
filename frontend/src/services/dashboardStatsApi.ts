/**
 * API des statistiques dashboard (cartes + donnees graphiques reelles).
 */

import { getJson } from "./httpClient";

export interface DailyStatsItem {
  day: string;
  date: string;
  calls: number;
  rdv: number;
  quotes: number;
  spam: number;
  voicemails?: number;
}

export interface DashboardStats {
  calls_today: number;
  rdv_count: number;
  quotes_count: number;
  suspects_count: number;
  total_calls: number;
  total_blocked: number;
  blocked_today: number;
  voicemails_today: number;
  voicemails_unread: number;
  voicemails_total: number;
  daily_series: DailyStatsItem[];
}

/**
 * Recupere les stats du dashboard depuis l'API (valeurs reelles backend).
 */
export async function fetchDashboardStats(): Promise<DashboardStats> {
  return getJson<DashboardStats>("/stats");
}
