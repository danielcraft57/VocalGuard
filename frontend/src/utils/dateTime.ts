/**
 * Parse une date API VocalGuard.
 *
 * Le backend stocke l'UTC naif (ex. `2026-08-27T20:28:38`) sans `Z`.
 * Sans correctif, le navigateur la traite comme heure locale → decalage (ex. -2h en CEST).
 *
 * @param value ISO date string depuis l'API.
 * @returns Date interpretee en UTC.
 */
export function parseApiUtcDate(value: string | null | undefined): Date {
  if (value == null) return new Date(NaN);
  const s = String(value).trim();
  if (!s) return new Date(NaN);
  if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(s)) {
    return new Date(s);
  }
  return new Date(`${s}Z`);
}

/**
 * Affiche une date API en heure locale fr-FR.
 *
 * @param value ISO date string depuis l'API.
 * @param options Options Intl (optionnel).
 * @returns Chaine locale ou tiret si invalide.
 */
export function formatApiDateTime(
  value: string | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  const d = parseApiUtcDate(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString(
    "fr-FR",
    options ?? {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    }
  );
}
