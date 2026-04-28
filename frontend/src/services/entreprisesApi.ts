import { getApiBaseUrl, getJson } from "./httpClient";

export interface Entreprise {
  id: number;
  name: string;
  categories?: string[];
  website?: string | null;
  phone_number?: string | null;
  phone_digits?: string | null;
  country?: string | null;
  city?: string | null;
  address_1?: string | null;
  address_2?: string | null;
  longitude?: number | null;
  latitude?: number | null;
  rating?: number | null;
  reviews_count?: number | null;
  created_at: string;
  updated_at: string;
}

export interface EntrepriseImportSummary {
  batch_id: number;
  original_filename?: string | null;
  total_rows: number;
  imported_rows: number;
  skipped_with_website: number;
  skipped_invalid: number;
  skipped_duplicates: number;
}

export interface EntrepriseListResponse {
  total: number;
  skip: number;
  limit: number;
  items: Entreprise[];
}

export async function fetchEntreprises(params?: {
  skip?: number;
  limit?: number;
  q?: string;
  country?: string;
  city?: string;
  category?: string;
  has_phone?: boolean;
}): Promise<EntrepriseListResponse> {
  const sp = new URLSearchParams();
  if (typeof params?.skip === "number") sp.set("skip", String(params.skip));
  if (typeof params?.limit === "number") sp.set("limit", String(params.limit));
  if (params?.q) sp.set("q", params.q);
  if (params?.country) sp.set("country", params.country);
  if (params?.city) sp.set("city", params.city);
  if (params?.category) sp.set("category", params.category);
  if (typeof params?.has_phone === "boolean") sp.set("has_phone", params.has_phone ? "true" : "false");

  const qs = sp.toString();
  return getJson<EntrepriseListResponse>(`/entreprises${qs ? `?${qs}` : ""}`);
}

export async function importEntreprisesXlsx(file: File, analyzePhone: boolean = true): Promise<EntrepriseImportSummary> {
  const baseUrl = getApiBaseUrl();
  const formData = new FormData();
  formData.append("file", file);

  const url = `${baseUrl}/entreprises/import?analyze_phone=${analyzePhone ? "true" : "false"}`;
  const res = await fetch(url, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Erreur import: ${res.status} ${text}`);
  }

  return (await res.json()) as EntrepriseImportSummary;
}

export async function deleteEntreprise(id: number): Promise<void> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}/entreprises/${id}`;
  const res = await fetch(url, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Erreur suppression: ${res.status} ${text}`);
  }
}

export async function deleteEntreprisesBulk(ids: number[]): Promise<{ deleted: number }> {
  const baseUrl = getApiBaseUrl();
  const sp = new URLSearchParams();
  for (const id of ids) sp.append("ids", String(id));
  const url = `${baseUrl}/entreprises?${sp.toString()}`;
  const res = await fetch(url, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Erreur suppression bulk: ${res.status} ${text}`);
  }
  return (await res.json()) as { deleted: number };
}

export async function fetchEntrepriseCallStats(id: number): Promise<{ total: number; by_status: Record<string, number> }> {
  return getJson<{ total: number; by_status: Record<string, number> }>(`/entreprises/${id}/call-stats`);
}

export interface EntreprisePhoneAnalysis {
  id: number;
  entreprise_id: number;
  phone_number: string;
  phone_digits?: string | null;
  phone_profile_id?: number | null;
  status: "queued" | "done" | "failed";
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PhoneNumberProfile {
  id: number;
  phone_number: string;
  normalized_number: string;
  country?: string | null;
  region?: string | null;
  city?: string | null;
  department?: string | null;
  postal_code?: string | null;
  line_type?: string | null;
  operator?: string | null;
  carrier?: string | null;
  is_company: boolean;
  name?: string | null;
  company_name?: string | null;
  reputation?: string | null;
  is_spam: boolean;
  is_scam: boolean;
  is_commercial: boolean;
  is_telemarketer: boolean;
  confidence?: number | null;
  last_checked_at?: string | null;
  created_at: string;
  updated_at: string;
  raw_data?: Record<string, unknown> | null;
}

export async function fetchEntreprisePhoneAnalyses(entrepriseId: number): Promise<EntreprisePhoneAnalysis[]> {
  return getJson<EntreprisePhoneAnalysis[]>(`/entreprises/${entrepriseId}/phone-analyses`);
}

export async function fetchOsintProfile(phoneNumber: string): Promise<PhoneNumberProfile> {
  return getJson<PhoneNumberProfile>(`/osint/profile/${encodeURIComponent(phoneNumber)}`);
}

