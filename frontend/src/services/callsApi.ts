import { getJson } from "./httpClient";

export interface Call {
  id: number;
  caller_id?: number | null;
  phone_number?: string | null;
  caller_name?: string | null;
  call_time: string;
  answer_time?: string | null;
  end_time?: string | null;
  status: string;
  duration?: number | null;
}

export interface CallListResponse {
  total: number;
  skip: number;
  limit: number;
  calls: Call[];
}

export interface OsintReputation {
  phone_number: string;
  reputation: string;
  is_spam: boolean;
  is_scam: boolean;
  is_commercial: boolean;
  is_telemarketer: boolean;
  confidence: number;
  sources: string[];
  recommendation: string;
  city?: string | null;
  region?: string | null;
  operator?: string | null;
}

export interface CallWithOsint extends Call {
  osint?: OsintReputation | null;
}

/**
 * Recupere la liste des appels avec la reputation OSINT depuis la base (un seul appel API, rapide).
 * Les numeros deja enrichis en base (migration --run-osint ou appels recents) auront leur reputation.
 */
export async function fetchCallsWithOsint(): Promise<CallWithOsint[]> {
  const data = await getJson<CallListResponse & { calls: CallWithOsint[] }>(
    "/calls?with_osint=true&limit=500"
  );
  return data.calls ?? [];
}

