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

/**
 * Affiche une date API en relatif (ex. « Il y a 5 min »).
 *
 * @param value ISO date string depuis l'API.
 * @param nowMs Horloge de reference (ms), pour tests ou rafraichissement UI.
 * @returns Libelle relatif en francais.
 */
export function formatApiRelativeTime(
  value: string | null | undefined,
  nowMs: number = Date.now()
): string {
  const d = parseApiUtcDate(value);
  if (Number.isNaN(d.getTime())) return "-";
  const diffSec = Math.max(0, Math.floor((nowMs - d.getTime()) / 1000));
  if (diffSec < 45) return "Il y a quelques secondes";
  if (diffSec < 90) return "Il y a 1 min";
  if (diffSec < 3600) return `Il y a ${Math.floor(diffSec / 60)} min`;
  if (diffSec < 7200) return "Il y a 1 h";
  if (diffSec < 86400) return `Il y a ${Math.floor(diffSec / 3600)} h`;
  if (diffSec < 172800) return "Il y a 1 jour";
  return `Il y a ${Math.floor(diffSec / 86400)} jours`;
}

/**
 * Formate une duree en minutes et secondes (ex. « 0 min 20 s », « 1 min 05 s »).
 *
 * @param totalSec Duree totale en secondes.
 * @returns Libelle lisible en francais.
 */
export function formatDurationMinSec(totalSec: number): string {
  if (!Number.isFinite(totalSec) || totalSec <= 0) return "0 min 00 s";
  const minutes = Math.floor(totalSec / 60);
  const seconds = Math.floor(totalSec % 60);
  return `${minutes} min ${seconds.toString().padStart(2, "0")} s`;
}
