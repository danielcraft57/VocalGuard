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
 * Liste les clients connus.
 */
export async function fetchClients(): Promise<Client[]> {
  return getJson<Client[]>("/clients");
}

