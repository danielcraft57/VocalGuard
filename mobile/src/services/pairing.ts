/**
 * Parse URI QR appairage VocalGuard.
 */

export interface ParsedPairUri {
  version: string;
  host: string;
  code: string;
}

/**
 * Extrait host/code depuis une query string (?host=...&code=...).
 */
function parsePairQuery(input: string): ParsedPairUri | null {
  const qIndex = input.indexOf("?");
  const query = qIndex >= 0 ? input.slice(qIndex + 1) : input;
  const params = new URLSearchParams(query);
  const host = params.get("host");
  const code = params.get("code");
  if (!host || !code) return null;
  return {
    version: params.get("v") ?? "1",
    host,
    code: code.toUpperCase(),
  };
}

/**
 * Parse vocalguard://pair?v=1&host=...&code=...
 *
 * @param uri URI scannee ou saisie.
 */
export function parsePairUri(uri: string): ParsedPairUri | null {
  const trimmed = uri.trim();
  if (!trimmed) return null;

  try {
    if (trimmed.startsWith("{")) {
      const json = JSON.parse(trimmed) as { v?: string; host?: string; code?: string };
      if (json.host && json.code) {
        return { version: json.v ?? "1", host: json.host, code: json.code.toUpperCase() };
      }
    }

    const fromQuery = parsePairQuery(trimmed);
    if (fromQuery) return fromQuery;

    const withoutScheme = trimmed.replace(/^vocalguard:\/\//i, "https://dummy/");
    const url = new URL(withoutScheme.replace(/^https:\/\/dummy\/pair\/?/i, "https://dummy/pair?"));
    const host = url.searchParams.get("host");
    const code = url.searchParams.get("code");
    if (!host || !code) return null;
    return {
      version: url.searchParams.get("v") ?? "1",
      host,
      code: code.toUpperCase(),
    };
  } catch {
    return parsePairQuery(trimmed);
  }
}

/**
 * Extrait le texte utile d un resultat scan camera.
 */
export function barcodeScanPayload(result: { data?: string | null; raw?: string | null }): string {
  return (result.data ?? result.raw ?? "").trim();
}
