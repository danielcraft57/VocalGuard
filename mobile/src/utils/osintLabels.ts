/**
 * Labels reputation OSINT en francais (aligne docs/APPELS_OSINT_UI.md).
 */

import type { CallOsintLite } from "../db/schema";

export type ReputationCategory = "good" | "bad" | "neutral" | "unknown";

/**
 * Categorise la reputation OSINT pour l affichage.
 *
 * @param osint Profil leger ou null.
 * @returns Categorie.
 */
export function getReputationCategory(osint?: CallOsintLite | null): ReputationCategory {
  if (!osint) return "unknown";
  const rep = (osint.reputation || "unknown").toLowerCase();
  if (rep === "high") return "good";
  if (rep === "low" || osint.is_spam || osint.is_scam) return "bad";
  if (rep === "neutral") return "neutral";
  return "unknown";
}

const REPUTATION_LABELS: Record<ReputationCategory, string> = {
  good: "Bonne",
  bad: "Risque",
  neutral: "Non evaluee",
  unknown: "Inconnue",
};

/**
 * Libelle francais de la reputation.
 *
 * @param osint Profil OSINT.
 * @returns Texte FR.
 */
export function getReputationLabel(osint?: CallOsintLite | null): string {
  return REPUTATION_LABELS[getReputationCategory(osint)];
}

/**
 * Couleur du chip reputation.
 *
 * @param category Categorie.
 * @returns Hex bg/fg.
 */
export function getReputationColor(category: ReputationCategory): { bg: string; fg: string } {
  if (category === "good") return { bg: "rgba(34, 197, 94, 0.15)", fg: "#22c55e" };
  if (category === "bad") return { bg: "rgba(239, 68, 68, 0.15)", fg: "#ef4444" };
  if (category === "neutral") return { bg: "rgba(148, 163, 184, 0.15)", fg: "#94a3b8" };
  return { bg: "rgba(100, 116, 139, 0.15)", fg: "#64748b" };
}

/**
 * Ligne meta OSINT (entreprise, operateur, ville).
 *
 * @param osint Profil.
 * @returns Texte ou null.
 */
export function formatOsintMeta(osint?: CallOsintLite | null): string | null {
  if (!osint) return null;
  const company = (osint.company_name || osint.name || "").trim();
  const parts: string[] = [];
  if (company) parts.push(company);
  const place = [osint.operator, osint.city].filter(Boolean).join(" · ");
  if (place) parts.push(place);
  return parts.length ? parts.join(" - ") : null;
}
