/**
 * Formateurs d affichage pour l app mobile.
 */

/**
 * Formate une date ISO en libelle court francais.
 *
 * @param iso Date ISO8601 ou null.
 * @returns Texte lisible (ex. "Aujourd hui 14:32").
 */
export function formatCallTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;

  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  const time = date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  if (sameDay) return `Aujourd'hui ${time}`;

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday =
    date.getFullYear() === yesterday.getFullYear() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getDate() === yesterday.getDate();
  if (isYesterday) return `Hier ${time}`;

  return date.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Formate une duree en secondes.
 *
 * @param seconds Duree en secondes.
 * @returns Texte mm:ss ou vide si 0.
 */
export function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return "";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/**
 * Duree style web (chips detail appel) : "0 min 14 s".
 *
 * @param seconds Duree en secondes.
 * @returns Libelle FR ou vide.
 */
export function formatDurationMinSec(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m} min ${s} s`;
}

/**
 * Date/heure style chip web detail : "23/09/2026 13:51".
 *
 * @param iso Date ISO ou null.
 * @returns Libelle FR ou vide.
 */
export function formatDetailDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Formate un numero FR en groupes lisibles.
 *
 * @param phone Numero brut.
 */
export function formatPhone(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  if (digits.length === 10) {
    return digits.replace(/(\d{2})(?=\d)/g, "$1 ").trim();
  }
  return phone;
}

/**
 * Libelle affichage pour un message vocal (nom, numero ou Inconnu).
 *
 * @param callerName Nom CID si connu.
 * @param callerNumber Numero appelant.
 */
export function voicemailCallerLabel(
  callerName: string | null | undefined,
  callerNumber: string | null | undefined,
): { title: string; subtitle: string | null } {
  const name = (callerName ?? "").trim();
  const rawNumber = (callerNumber ?? "").trim();
  const number = rawNumber ? formatPhone(rawNumber) : "";

  if (name && number) {
    return { title: name, subtitle: number };
  }
  if (name) {
    return { title: name, subtitle: null };
  }
  if (number) {
    return { title: number, subtitle: null };
  }
  return { title: "Inconnu", subtitle: null };
}
