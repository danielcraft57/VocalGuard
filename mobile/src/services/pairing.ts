/**
 * Parse URI QR appairage VocalGuard.
 */

export interface ParsedPairUri {
  version: string;
  host: string;
  code: string;
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
    const withoutScheme = trimmed.replace(/^vocalguard:\/\//, "https://dummy/");
    const url = new URL(withoutScheme.replace(/^https:\/\/dummy\/pair/, "https://dummy/pair"));
    const host = url.searchParams.get("host");
    const code = url.searchParams.get("code");
    if (!host || !code) return null;
    return {
      version: url.searchParams.get("v") ?? "1",
      host,
      code: code.toUpperCase(),
    };
  } catch {
    return null;
  }
}
