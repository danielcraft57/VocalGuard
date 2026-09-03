import { getJson } from "./httpClient";

export interface Client {
  id: number;
  entreprise_id?: number | null;
  phone_number: string;
  email?: string | null;
  name?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Liste les clients connus (pagine cote API, defaut 200).
 */
export async function fetchClients(opts?: { skip?: number; limit?: number }): Promise<Client[]> {
  const params = new URLSearchParams();
  if (opts?.skip != null) params.set("skip", String(opts.skip));
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return getJson<Client[]>(`/clients${qs ? `?${qs}` : ""}`);
}

