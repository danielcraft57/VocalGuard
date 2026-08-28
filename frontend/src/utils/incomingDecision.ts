import type { IncomingProfileKind } from "../components/mui/VgProfileChip";

/**
 * Parse le resume policy renvoye par /telephony/status.
 *
 * @param raw Chaine type ``screened | preset:voicemail | rings=0 | ignore=false``.
 * @returns Profil et libelle lisible, ou null si vide.
 */
export function parseIncomingDecision(raw?: string | null): {
  profile: IncomingProfileKind;
  label: string;
} | null {
  if (!raw || !raw.trim()) return null;
  const parts = raw.split("|").map((p) => p.trim());
  const profileRaw = (parts[0] || "screened").toLowerCase();
  const profile: IncomingProfileKind =
    profileRaw === "permitted" || profileRaw === "blocked" ? profileRaw : "screened";
  const source = parts[1] || "";
  const rings = parts.find((p) => p.startsWith("rings="))?.replace("rings=", "") ?? "?";
  const ignore = parts.find((p) => p.startsWith("ignore="))?.replace("ignore=", "") ?? "?";
  const sourceLabel = source.replace(/^preset:/, "preset ");
  return {
    profile,
    label: `${sourceLabel || "policy"} · ${rings} sonnerie(s) · ignore=${ignore}`
  };
}
