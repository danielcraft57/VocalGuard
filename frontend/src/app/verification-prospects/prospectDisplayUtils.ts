import type { ProspectPhone } from "../../services/prospectPhonesApi";

/**
 * Ville affichee a l'utilisateur (donnee Excel en priorite, pas le nom de fichier).
 *
 * @param row Prospect.
 */
export function prospectDisplayCity(row: ProspectPhone): string {
  const fromRow = (row.city ?? "").trim();
  if (fromRow) return fromRow;
  const fromImport = (row.source_city ?? "").trim();
  return fromImport || "—";
}

/**
 * Deduit un libelle ville depuis le nom de fichier (stem sans extension).
 */
export function cityLabelFromUploadFilename(filename: string): string | null {
  const base = filename.replace(/\\/g, "/").split("/").pop() ?? filename;
  const stem = base.replace(/\.xlsx$/i, "").trim();
  return stem || null;
}
