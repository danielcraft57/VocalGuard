import type { PhoneNumberProfile } from "./entreprisesApi";
import { fetchOsintProfile } from "./entreprisesApi";
import { getApiBaseUrl, getJson } from "./httpClient";

export type ProspectPhoneVerificationStatus =
  | "pending"
  | "line_ok"
  | "line_fail"
  | "voicemail"
  | "company_ok"
  | "company_mismatch"
  | "skipped";

export interface ProspectPhone {
  id: number;
  name: string;
  phone_number?: string | null;
  phone_digits?: string | null;
  source_city?: string | null;
  country?: string | null;
  city?: string | null;
  postal_code?: string | null;
  address_1?: string | null;
  address_2?: string | null;
  longitude?: number | null;
  latitude?: number | null;
  rating?: number | null;
  reviews_count?: number | null;
  google_categories_raw?: string | null;
  category_translate_raw?: string | null;
  categories: string[];
  google_types: string[];
  website?: string | null;
  phone_profile_id?: number | null;
  osint_status: string;
  prospectlab_status: string;
  prospectlab_entreprise_id?: number | null;
  prospectlab_name?: string | null;
  osint_company_name?: string | null;
  osint_reputation?: string | null;
  osint_operator?: string | null;
  osint_region?: string | null;
  name_match_status?: string | null;
  enriched_at?: string | null;
  verification_status: ProspectPhoneVerificationStatus;
  verification_notes?: string | null;
  verified_at?: string | null;
  last_call_id?: number | null;
  import_batch_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface ProspectPhoneListResponse {
  total: number;
  skip: number;
  limit: number;
  items: ProspectPhone[];
}

export interface ProspectPhoneImportSummary {
  batch_id: number;
  original_filename?: string | null;
  source_city?: string | null;
  total_rows: number;
  imported_rows: number;
  skipped_with_website: number;
  skipped_invalid: number;
  skipped_duplicates: number;
  phase: string;
  enrich_total: number;
  enrich_done: number;
  enrich_failed: number;
  enrich_queued: number;
  last_error?: string | null;
}

export interface ProspectPhonesSummary {
  total: number;
  by_status: Record<string, number>;
}

export async function fetchProspectPhones(
  params?: {
    skip?: number;
    limit?: number;
    q?: string;
    source_city?: string;
    city?: string;
    verification_status?: ProspectPhoneVerificationStatus;
    osint_status?: string;
    prospectlab_status?: string;
    name_match_status?: string;
    import_batch_id?: number;
  },
  signal?: AbortSignal
): Promise<ProspectPhoneListResponse> {
  const sp = new URLSearchParams();
  if (typeof params?.skip === "number") sp.set("skip", String(params.skip));
  if (typeof params?.limit === "number") sp.set("limit", String(params.limit));
  if (params?.q) sp.set("q", params.q);
  if (params?.source_city) sp.set("source_city", params.source_city);
  if (params?.city) sp.set("city", params.city);
  if (params?.verification_status) sp.set("verification_status", params.verification_status);
  if (params?.osint_status) sp.set("osint_status", params.osint_status);
  if (params?.prospectlab_status) sp.set("prospectlab_status", params.prospectlab_status);
  if (params?.name_match_status) sp.set("name_match_status", params.name_match_status);
  if (typeof params?.import_batch_id === "number") sp.set("import_batch_id", String(params.import_batch_id));
  const qs = sp.toString();
  return getJson<ProspectPhoneListResponse>(`/prospect-phones${qs ? `?${qs}` : ""}`, signal);
}

export async function fetchProspectPhoneSourceCities(signal?: AbortSignal): Promise<string[]> {
  return getJson<string[]>("/prospect-phones/source-cities", signal);
}

export async function fetchProspectPhonesSummary(signal?: AbortSignal): Promise<ProspectPhonesSummary> {
  return getJson<ProspectPhonesSummary>("/prospect-phones/stats/summary", signal);
}

export interface ProspectEnrichCapabilities {
  osint_remote: boolean;
  osint_host?: string | null;
  enrich_engine: string;
  default_parallel: number;
  celery_available: boolean;
}

/**
 * Capacites OSINT (local vs node15, parallelisme).
 */
export async function fetchProspectEnrichCapabilities(signal?: AbortSignal): Promise<ProspectEnrichCapabilities> {
  return getJson<ProspectEnrichCapabilities>("/prospect-phones/enrich-capabilities", signal);
}

async function readApiError(res: Response): Promise<string> {
  const text = await res.text().catch(() => "");
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) return body.detail.trim();
  } catch {
    // pas du JSON
  }
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.slice(0, 400) || `HTTP ${res.status}`;
}

export function explainFetchFailure(err: unknown, url: string): string {
  const raw = err instanceof Error ? err.message : String(err || "erreur");
  if (/failed to fetch|networkerror|load failed/i.test(raw)) {
    return `Pas de reponse du backend (${url}). Il a peut-etre plante : regarde le journal ci-dessous, ou logs/backend.err.log.`;
  }
  return raw;
}

export async function importProspectPhonesXlsx(file: File, runOsint = true): Promise<ProspectPhoneImportSummary> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}/prospect-phones/import?run_osint=${runOsint ? "true" : "false"}`;
  let res: Response;
  try {
    const formData = new FormData();
    formData.append("file", file);
    res = await fetch(url, { method: "POST", body: formData });
  } catch (err) {
    throw new Error(explainFetchFailure(err, url));
  }
  if (!res.ok) {
    throw new Error(`Import refuse (${res.status}) : ${await readApiError(res)}`);
  }
  return (await res.json()) as ProspectPhoneImportSummary;
}

export async function fetchProspectServerLogs(): Promise<{ at: string; level: string; message: string }[]> {
  const data = await getJson<{ lines: { at: string; level: string; message: string }[] }>("/prospect-phones/server-logs");
  return data.lines ?? [];
}

export async function importProspectPhonesDirectory(directoryPath?: string): Promise<unknown> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/prospect-phones/import-directory`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ directory_path: directoryPath ?? null }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Erreur import dossier: ${res.status} ${text}`);
  }
  return await res.json();
}

export async function fetchProspectImportBatch(batchId: number): Promise<ProspectPhoneImportSummary> {
  return getJson<ProspectPhoneImportSummary>(`/prospect-phones/import-batches/${batchId}`);
}

export interface ProspectPhoneDetail {
  prospect: ProspectPhone;
  osint_profile: PhoneNumberProfile | null;
}

/**
 * Lit un prospect (route de base, toujours presente).
 *
 * @param id Identifiant prospect.
 */
export async function fetchProspectPhone(id: number): Promise<ProspectPhone> {
  return getJson<ProspectPhone>(`/prospect-phones/${id}`);
}

/**
 * Tente de charger le profil OSINT persiste pour un numero.
 */
async function loadOsintProfileOptional(phone?: string | null): Promise<PhoneNumberProfile | null> {
  const raw = (phone ?? "").trim();
  if (!raw) return null;
  const variants: string[] = [raw, raw.replace(/\s/g, "")];
  const digits = raw.replace(/\D/g, "");
  if (digits.startsWith("33") && digits.length === 11) {
    variants.push(`+${digits}`, `0${digits.slice(2)}`);
  } else if (digits.startsWith("0") && digits.length === 10) {
    variants.push(`+33${digits.slice(1)}`);
  }
  const tried = new Set<string>();
  for (const v of variants) {
    if (!v || tried.has(v)) continue;
    tried.add(v);
    try {
      return await fetchOsintProfile(v);
    } catch {
      // essayer autre format
    }
  }
  return null;
}

/**
 * Assemble prospect + profil OSINT (plusieurs appels si besoin).
 */
async function assembleProspectDetail(prospect: ProspectPhone): Promise<ProspectPhoneDetail> {
  const osint_profile = await loadOsintProfileOptional(prospect.phone_number);
  return { prospect, osint_profile };
}

/**
 * Charge un prospect et son profil OSINT (modal detail).
 *
 * @param id Identifiant prospect.
 */
export async function fetchProspectPhoneDetail(id: number): Promise<ProspectPhoneDetail> {
  try {
    const full = await getJson<ProspectPhoneDetail>(`/prospect-phones/${id}/detail`);
    if (!full.osint_profile && full.prospect.phone_number) {
      const profile = await loadOsintProfileOptional(full.prospect.phone_number);
      if (profile) {
        return { ...full, osint_profile: profile };
      }
    }
    return full;
  } catch (err) {
    const msg = err instanceof Error ? err.message : "";
    const missingRoute = /not found/i.test(msg) || /\b404\b/.test(msg);
    if (!missingRoute) {
      throw err;
    }
    const prospect = await fetchProspectPhone(id);
    return assembleProspectDetail(prospect);
  }
}

/**
 * Relance l'enrichissement OSINT + ProspectLab pour une ligne.
 *
 * @param id Identifiant prospect.
 */
export async function enrichProspectPhoneAgain(id: number): Promise<ProspectPhoneDetail> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/prospect-phones/${id}/enrich`, { method: "POST" });
  if (!res.ok) {
    const detail = await readApiError(res);
    if (res.status === 404) {
      throw new Error(
        "Relance OSINT indisponible sur cette API (redemarre le backend pour activer /prospect-phones/.../enrich).",
      );
    }
    throw new Error(detail);
  }
  const data = (await res.json()) as ProspectPhoneDetail;
  if (!data.osint_profile && data.prospect.phone_number) {
    const profile = await loadOsintProfileOptional(data.prospect.phone_number);
    if (profile) {
      return { ...data, osint_profile: profile };
    }
  }
  return data;
}

export async function updateProspectPhone(
  id: number,
  payload: Partial<Pick<
    ProspectPhone,
    | "name"
    | "phone_number"
    | "source_city"
    | "city"
    | "postal_code"
    | "address_1"
    | "address_2"
    | "website"
    | "country"
    | "verification_status"
    | "verification_notes"
  >> & { last_call_id?: number | null }
): Promise<ProspectPhone> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/prospect-phones/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readApiError(res));
  }
  return (await res.json()) as ProspectPhone;
}

/**
 * Cree un prospect a la main.
 *
 * @param payload Nom et champs optionnels.
 * @returns Prospect cree.
 */
export async function createProspectPhone(
  payload: {
    name: string;
    phone_number?: string | null;
    source_city?: string | null;
    address_1?: string | null;
    address_2?: string | null;
    verification_status?: ProspectPhoneVerificationStatus;
    verification_notes?: string | null;
  }
): Promise<ProspectPhone> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/prospect-phones`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readApiError(res));
  }
  return (await res.json()) as ProspectPhone;
}

/**
 * Supprime un prospect.
 *
 * @param id Identifiant.
 */
export async function deleteProspectPhone(id: number): Promise<void> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/prospect-phones/${id}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(await readApiError(res));
  }
}

/**
 * Vide tous les resultats (prospects, categories, lots).
 *
 * @returns Nombre de prospects supprimes.
 */
export async function deleteAllProspectPhones(): Promise<number> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/prospect-phones`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(await readApiError(res));
  }
  const body = (await res.json()) as { deleted?: number };
  return body.deleted ?? 0;
}
