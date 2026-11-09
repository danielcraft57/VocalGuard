import { getJson, getApiBaseUrl } from "./httpClient";

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
 *
 * @param opts Pagination.
 * @param signal AbortSignal optionnel.
 */
export async function fetchClients(
  opts?: { skip?: number; limit?: number },
  signal?: AbortSignal
): Promise<Client[]> {
  const params = new URLSearchParams();
  if (opts?.skip != null) params.set("skip", String(opts.skip));
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return getJson<Client[]>(`/clients${qs ? `?${qs}` : ""}`, signal);
}

export interface CreateClientPayload {
  phone_number: string;
  name?: string | null;
  email?: string | null;
  notes?: string | null;
  entreprise_id?: number | null;
}

/**
 * Cree un contact client (personne).
 *
 * @param payload Donnees contact.
 */
export async function createClient(payload: CreateClientPayload): Promise<Client> {
  const res = await fetch(`${getApiBaseUrl()}/clients`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      phone_number: payload.phone_number,
      name: payload.name ?? null,
      email: payload.email ?? null,
      notes: payload.notes ?? null,
      entreprise_id: payload.entreprise_id ?? null
    })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Erreur ${res.status}`);
  }
  return res.json();
}

