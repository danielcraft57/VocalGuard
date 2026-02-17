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
 * Liste les devis existants.
 */
export async function fetchQuotes(): Promise<Quote[]> {
  return getJson<Quote[]>("/quotes");
}

