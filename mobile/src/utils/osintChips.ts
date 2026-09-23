/**
 * Construction des chips OSINT (alignee web CallDetailModal).
 */
import type { CallOsintLite } from "../db/schema";

export type OsintChipVariant = "primary" | "neutral" | "warn" | "danger";

export type OsintChip = {
  key: string;
  label: string;
  variant: OsintChipVariant;
};

/**
 * Construit la liste de chips OSINT pour l affichage detail.
 *
 * @param osint Profil leger ou null.
 * @returns Chips (vide si pas de profil).
 * @example
 * buildOsintChips({ operator: "Orange", reputation: "neutral" })
 */
export function buildOsintChips(osint: CallOsintLite | null | undefined): OsintChip[] {
  if (!osint) return [];
  const company = (osint.company_name || osint.name || "").trim();
  const place = [osint.city, osint.region].filter(Boolean).join(", ");
  const rec = (osint.recommendation || "review").trim().toLowerCase();
  const reputation = (osint.reputation || "unknown").trim().toLowerCase();

  const chips: OsintChip[] = [];
  if (company) chips.push({ key: "co", label: company, variant: "primary" });
  chips.push({ key: "rep", label: `${rec} / ${reputation}`, variant: "neutral" });
  if (osint.operator) chips.push({ key: "op", label: osint.operator, variant: "neutral" });
  if (place) chips.push({ key: "place", label: place, variant: "neutral" });
  if (osint.is_spam) chips.push({ key: "spam", label: "Spam", variant: "warn" });
  if (osint.is_scam) chips.push({ key: "scam", label: "Arnaque", variant: "danger" });
  return chips;
}
