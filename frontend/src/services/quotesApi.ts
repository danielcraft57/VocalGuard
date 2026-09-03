import { getJson } from "./httpClient";

export interface QuoteLine {
  description: string;
  quantity: number;
  unit_price: number;
}

export interface Quote {
  id: number;
  customer_id?: number | null;
  phone_number?: string | null;
  title: string;
  lines: QuoteLine[];
  notes?: string | null;
  status: string;
  total_ht: number;
  total_ttc: number;
  created_at: string;
}

/**
 * Liste les devis existants (pagine, defaut 100).
 */
export async function fetchQuotes(opts?: { skip?: number; limit?: number }): Promise<Quote[]> {
  const params = new URLSearchParams();
  if (opts?.skip != null) params.set("skip", String(opts.skip));
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return getJson<Quote[]>(`/quotes${qs ? `?${qs}` : ""}`);
}

