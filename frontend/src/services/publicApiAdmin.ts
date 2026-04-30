import { getApiBaseUrl } from "./httpClient";

export interface PublicApiToken {
  id: number;
  name: string;
  app_url?: string | null;
  token?: string | null;
  token_preview?: string | null;
  is_active: boolean;
  can_read_agenda: boolean;
  can_write_agenda: boolean;
  can_write_entreprises: boolean;
  can_manage_tokens: boolean;
  created_at: string;
  last_used_at?: string | null;
}

export interface PublicApiDocsEndpoint {
  method: string;
  path: string;
  permission: string;
  title?: string;
  description?: string;
  request?: {
    headers?: string[];
    query?: Record<string, any>;
    body?: any;
  };
  responses?: Record<string, { example?: any }>;
}

export interface PublicApiDocsPayload {
  name: string;
  base_url: string;
  auth: {
    headers: string[];
    admin_header?: string;
  };
  endpoints: PublicApiDocsEndpoint[];
}

export interface PublicApiTokenCreatePayload {
  app_url: string;
  name?: string;
  can_read_agenda: boolean;
  can_write_agenda: boolean;
  can_write_entreprises: boolean;
  can_manage_tokens: boolean;
}

function buildHeaders(): HeadersInit {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const safeAdminToken = (process.env.NEXT_PUBLIC_PUBLIC_API_ADMIN_TOKEN ?? "").trim();
  if (safeAdminToken) headers["x-admin-token"] = safeAdminToken;
  return headers;
}

export async function fetchPublicApiDocs(): Promise<PublicApiDocsPayload> {
  const res = await fetch(`${getApiBaseUrl()}/tokens/docs`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Impossible de charger la doc API (${res.status}).`);
  }
  return (await res.json()) as PublicApiDocsPayload;
}

export async function listPublicTokens(): Promise<PublicApiToken[]> {
  const res = await fetch(`${getApiBaseUrl()}/tokens`, {
    method: "GET",
    cache: "no-store",
    headers: buildHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Impossible de lister les tokens (${res.status}).`);
  }
  return (await res.json()) as PublicApiToken[];
}

export async function createPublicToken(
  payload: PublicApiTokenCreatePayload,
): Promise<PublicApiToken> {
  const res = await fetch(`${getApiBaseUrl()}/tokens`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Impossible de créer le token (${res.status}).`);
  }
  return (await res.json()) as PublicApiToken;
}

export async function revokePublicToken(tokenId: number): Promise<void> {
  const res = await fetch(`${getApiBaseUrl()}/tokens/${tokenId}/revoke`, {
    method: "POST",
    headers: buildHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Impossible de révoquer le token (${res.status}).`);
  }
}

export async function deletePublicToken(tokenId: number): Promise<void> {
  const res = await fetch(`${getApiBaseUrl()}/tokens/${tokenId}`, {
    method: "DELETE",
    headers: buildHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Impossible de supprimer le token (${res.status}).`);
  }
}

export async function revealPublicToken(tokenId: number): Promise<PublicApiToken> {
  const res = await fetch(`${getApiBaseUrl()}/tokens/${tokenId}/reveal`, {
    method: "GET",
    headers: buildHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Impossible de voir le token (${res.status}).`);
  }
  return (await res.json()) as PublicApiToken;
}

export async function patchPublicToken(tokenId: number, patch: Partial<PublicApiTokenCreatePayload & { is_active?: boolean }>): Promise<PublicApiToken> {
  const res = await fetch(`${getApiBaseUrl()}/tokens/${tokenId}`, {
    method: "PATCH",
    headers: buildHeaders(),
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    throw new Error(`Impossible de modifier le token (${res.status}).`);
  }
  return (await res.json()) as PublicApiToken;
}
