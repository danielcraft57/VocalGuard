/**
 * Groupes Material pour les intents KB (entrant vs commercial).
 */

import type { KbIntent } from "../../services/kbApi";
import type { KbProfile } from "../../services/kbUiPersist";

export type IntentGroupId =
  | "presentation"
  | "qualification"
  | "objections"
  | "closing"
  | "accueil"
  | "contact"
  | "rdv"
  | "commercial"
  | "support"
  | "infos"
  | "autre";

export type IntentGroup = {
  id: IntentGroupId;
  label: string;
  hint: string;
};

/** Groupes appels entrants (catalogue a reconstruire). */
export const INBOUND_GROUPS: IntentGroup[] = [
  { id: "accueil", label: "Accueil & cloture", hint: "Salutations, aide, fin d'appel" },
  { id: "contact", label: "Coordonnees", hint: "Email, rappel, fiches contact" },
  { id: "rdv", label: "Rendez-vous", hint: "Prise, report, annulation" },
  { id: "commercial", label: "Commercial", hint: "Devis, offres, partenariats" },
  { id: "support", label: "Support", hint: "Urgence, SAV, factures" },
  { id: "infos", label: "Infos pratiques", hint: "Horaires, acces, site" },
  { id: "autre", label: "Autres", hint: "Le reste du catalogue" }
];

/** Groupes appels commerciaux (argumentaire). */
export const OUTBOUND_GROUPS: IntentGroup[] = [
  {
    id: "presentation",
    label: "Presentation",
    hint: "Ouverture, identite, feu vert"
  },
  {
    id: "qualification",
    label: "Qualification",
    hint: "Site, leads, valeur"
  },
  {
    id: "objections",
    label: "Objections",
    hint: "Pas le temps, deja un site, prix, spam"
  },
  {
    id: "closing",
    label: "Closing",
    hint: "Audit, creneau, lien, rappel"
  },
  {
    id: "autre",
    label: "Cloture & divers",
    hint: "Pas interesse, au revoir, incompris"
  }
];

/** Compat anciens imports. */
export const INTENT_GROUPS = INBOUND_GROUPS;

const INBOUND_TAG_GROUP: Record<string, IntentGroupId> = {
  salutation: "accueil",
  silence_attente: "accueil",
  aide_menu: "accueil",
  remerciements: "accueil",
  incompris: "accueil",
  hors_sujet: "accueil",
  insulte: "accueil",
  fin: "accueil",
  spam_demarchage: "accueil",
  langue_anglaise: "accueil",
  affirmation: "accueil",
  negation: "accueil",
  attente_patience: "accueil",
  clarte_audio: "accueil",
  qui_etes_vous: "accueil",
  mauvais_numero: "accueil",
  je_rappellerai: "accueil",
  prendre_coordonnees: "contact",
  contact_email: "contact",
  rappel_callback: "contact",
  changement_coordonnees: "contact",
  parler_humain: "contact",
  pour_personne: "contact",
  parler_direction: "contact",
  contacter_personne: "contact",
  presence_demande: "contact",
  contact_sms: "contact",
  numero_entreprise: "contact",
  prise_rdv: "rdv",
  annuler_rdv: "rdv",
  deplacer_rdv: "rdv",
  confirmer_rdv: "rdv",
  essai_demo: "rdv",
  tarifs_devis: "commercial",
  services_info: "commercial",
  catalogue_brochure: "commercial",
  site_web: "commercial",
  partenariat: "commercial",
  recrutement: "commercial",
  formation: "commercial",
  nouveau_client: "commercial",
  abonnement: "commercial",
  delai_traitement: "commercial",
  urgence: "support",
  sav_technique: "support",
  reclamation: "support",
  facture_paiement: "support",
  suivi_commande: "support",
  deja_client: "support",
  absent_laisser_message: "support",
  resiliation: "support",
  retour_remboursement: "support",
  garantie: "support",
  horaires: "infos",
  adresse_acces: "infos",
  parking_acces: "infos",
  cgv_mentions: "infos",
  reseaux_sociaux: "infos",
  fermeture_vacances: "infos"
};

const OUTBOUND_TAG_GROUP: Record<string, IntentGroupId> = {
  out_presentation: "presentation",
  out_who_are_you: "presentation",
  out_go_ahead: "presentation",
  out_qualify_website: "qualification",
  out_qualify_leads: "qualification",
  out_value_pitch: "qualification",
  out_busy: "objections",
  out_objection_no_time: "objections",
  out_objection_has_site: "objections",
  out_objection_price: "objections",
  out_objection_spam: "objections",
  out_callback_later: "closing",
  out_closing_audit: "closing",
  out_closing_slot: "closing",
  out_closing_link: "closing",
  out_not_interested: "autre",
  out_goodbye: "autre",
  out_unclear: "autre"
};

/**
 * Groupes UI selon le profil catalogue.
 *
 * @param profile inbound | outbound_commercial.
 * @returns Liste de groupes.
 */
export function groupsForProfile(profile: KbProfile): IntentGroup[] {
  return profile === "outbound_commercial" ? OUTBOUND_GROUPS : INBOUND_GROUPS;
}

/**
 * Id du groupe ouvert par defaut pour un profil.
 *
 * @param profile Catalogue.
 * @returns Id groupe.
 */
export function defaultExpandedGroupId(profile: KbProfile): IntentGroupId {
  return profile === "outbound_commercial" ? "presentation" : "accueil";
}

/**
 * Assigne un intent a un groupe UI.
 *
 * @param intent Intent.
 * @param profile Catalogue courant.
 * @returns Id groupe.
 */
export function groupIdForIntent(
  intent: KbIntent,
  profile: KbProfile = "inbound"
): IntentGroupId {
  if (profile === "outbound_commercial") {
    return OUTBOUND_TAG_GROUP[intent.tag] || "presentation";
  }
  return INBOUND_TAG_GROUP[intent.tag] || "autre";
}

/**
 * Filtre + regroupe les intents pour l'UI.
 *
 * @param intents Catalogue.
 * @param query Recherche libre.
 * @param groupFilter Groupe ou "all".
 * @param profile Catalogue (choisit les groupes).
 * @returns Map groupe -> intents.
 */
export function groupIntents(
  intents: KbIntent[],
  query: string,
  groupFilter: IntentGroupId | "all",
  profile: KbProfile = "inbound"
): Record<IntentGroupId, KbIntent[]> {
  const groups = groupsForProfile(profile);
  const q = query.trim().toLowerCase();
  const out = Object.fromEntries(groups.map((g) => [g.id, [] as KbIntent[]])) as Record<
    IntentGroupId,
    KbIntent[]
  >;

  for (const intent of intents) {
    const gid = groupIdForIntent(intent, profile);
    if (groupFilter !== "all" && gid !== groupFilter) continue;
    if (q) {
      const hay = [
        intent.tag,
        intent.action || "",
        ...intent.patterns,
        ...intent.responses
      ]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(q)) continue;
    }
    if (!out[gid]) out[gid] = [];
    out[gid].push(intent);
  }

  for (const g of groups) {
    out[g.id].sort((a, b) => b.priority - a.priority || a.tag.localeCompare(b.tag));
  }
  return out;
}
