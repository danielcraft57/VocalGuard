import { getJson } from "./httpClient";

export interface Appointment {
  id: number;
  customer_id?: number | null;
  phone_number?: string | null;
  title: string;
  start_time: string;
  end_time: string;
  location?: string | null;
  status: string;
  service_type?: string | null;
  notes?: string | null;
  created_at: string;
}

/**
 * Retourne la liste des rendez-vous depuis l'API.
 */
export async function fetchAppointments(): Promise<Appointment[]> {
  return getJson<Appointment[]>("/appointments");
}

