import { getApiBaseUrl, getJson } from "./httpClient";

export interface Appointment {
  id: number;
  customer_id?: number | null;
  entreprise_id?: number | null;
  phone_number?: string | null;
  title: string;
  start_time: string;
  end_time: string;
  location?: string | null;
  status: string;
  service_type?: string | null;
  agenda_tag?: string | null;
  display_icon?: string | null;
  display_color?: string | null;
  is_all_day?: boolean;
  notes?: string | null;
  created_at: string;
}

/**
 * Retourne la liste des rendez-vous depuis l'API.
 */
export async function fetchAppointments(): Promise<Appointment[]> {
  return getJson<Appointment[]>("/agenda");
}

export interface AppointmentPayload {
  customer_id?: number | null;
  source_call_id?: number | null;
  entreprise_id?: number | null;
  phone_number?: string | null;
  title: string;
  start_time: string;
  end_time: string;
  location?: string | null;
  status?: string;
  service_type?: string | null;
  agenda_tag?: string | null;
  display_icon?: string | null;
  display_color?: string | null;
  is_all_day?: boolean;
  notes?: string | null;
}

export interface AppointmentSettings {
  id: number;
  timezone: string;
  work_day_start: string;
  work_day_end: string;
  slot_minutes: number;
  monday_enabled: boolean;
  tuesday_enabled: boolean;
  wednesday_enabled: boolean;
  thursday_enabled: boolean;
  friday_enabled: boolean;
  saturday_enabled: boolean;
  sunday_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface NonWorkingDay {
  id: number;
  date: string;
  label: string;
  created_at: string;
}

async function requestJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Erreur API ${method} ${path}: ${res.status}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export function createAppointment(payload: AppointmentPayload): Promise<Appointment> {
  return requestJson<Appointment>("/agenda", "POST", payload);
}

export function updateAppointment(id: number, payload: Partial<AppointmentPayload>): Promise<Appointment> {
  return requestJson<Appointment>(`/agenda/${id}`, "PATCH", payload);
}

export function deleteAppointment(id: number): Promise<void> {
  return requestJson<void>(`/agenda/${id}`, "DELETE");
}

export function fetchAppointmentSettings(): Promise<AppointmentSettings> {
  return getJson<AppointmentSettings>("/agenda/settings");
}

export function updateAppointmentSettings(
  payload: Omit<AppointmentSettings, "id" | "created_at" | "updated_at">
): Promise<AppointmentSettings> {
  return requestJson<AppointmentSettings>("/agenda/settings", "PUT", payload);
}

export function fetchNonWorkingDays(): Promise<NonWorkingDay[]> {
  return getJson<NonWorkingDay[]>("/agenda/non-working-days");
}

export function createNonWorkingDay(payload: { date: string; label: string }): Promise<NonWorkingDay> {
  return requestJson<NonWorkingDay>("/agenda/non-working-days", "POST", payload);
}

export function deleteNonWorkingDay(id: number): Promise<void> {
  return requestJson<void>(`/agenda/non-working-days/${id}`, "DELETE");
}

