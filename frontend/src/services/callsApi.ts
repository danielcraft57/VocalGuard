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
}

export interface CallWithOsint extends Call {
  osint?: OsintReputation | null;
}

/**
 * Recupere la liste des appels et tente d'enrichir chaque numero
 * avec une reputation OSINT basique.
 *
 * @returns Liste des appels enrichis.
 */
export async function fetchCallsWithOsint(): Promise<CallWithOsint[]> {
  const data = await getJson<CallListResponse>("/calls");

  const calls = data.calls ?? [];

  const enriched: CallWithOsint[] = await Promise.all(
    calls.map(async (call) => {
      const phone = call.phone_number;
      if (!phone) {
        return { ...call, osint: null };
      }

      try {
        const osint = await getJson<OsintReputation>(`/osint/reputation/${encodeURIComponent(phone)}`);
        return { ...call, osint };
      } catch {
        // En cas d'erreur OSINT, on garde quand meme l'appel.
        return { ...call, osint: null };
      }
    })
  );

  return enriched;
}

