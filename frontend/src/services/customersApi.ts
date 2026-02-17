import { getJson } from "./httpClient";

export interface Customer {
  id: number;
  phone_number: string;
  email?: string | null;
  name?: string | null;
  company_name?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Liste les clients connus.
 */
export async function fetchCustomers(): Promise<Customer[]> {
  return getJson<Customer[]>("/customers");
}

