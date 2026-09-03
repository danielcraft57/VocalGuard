import type { IncomingProfileKind } from "../components/mui/VgProfileChip";
import type { CallWithOsint } from "../services/callsApi";

/**
 * Profil policy d'un appel entrant (extra_data ou heuristique statut).
 *
 * @param call Ligne appel API.
 * @returns permitted | screened | blocked.
 */
export function getCallIncomingProfile(call: CallWithOsint): IncomingProfileKind {
  const ex = call.extra_data;
  if (ex && typeof ex === "object") {
    const raw = String((ex as { incoming_profile?: string }).incoming_profile || "").toLowerCase();
    if (raw === "permitted" || raw === "blocked" || raw === "screened") {
      return raw;
    }
  }
  const status = (call.status || "").toLowerCase();
  if (status === "blocked") return "blocked";
  if (status === "answered" || status === "completed") return "permitted";
  return "screened";
}

/**
 * Source policy stockee sur l'appel (preset:voicemail, etc.).
 *
 * @param call Ligne appel.
 * @returns Chaine source ou null.
 */
export function getCallPolicySource(call: CallWithOsint): string | null {
  const ex = call.extra_data;
  if (!ex || typeof ex !== "object") return null;
  const src = (ex as { incoming_policy_source?: string }).incoming_policy_source;
  return src ? String(src) : null;
}

/**
 * Texte d'aide UX pour le chip de traitement d'appel.
 *
 * @param profile Profil incoming.
 * @returns Phrase courte pour tooltip.
 */
export function getIncomingProfileHint(profile: IncomingProfileKind): string {
  if (profile === "permitted") {
    return "Appel autorise : traite selon vos regles (fixe / repondeur).";
  }
  if (profile === "blocked") {
    return "Appel bloque : refuse selon le filtrage.";
  }
  return "Appel filtre : passe par le repondeur / historique.";
}
