/**
 * Groupes Material pour les intents KB.
 */

import type { KbIntent } from "../../services/kbApi";

export type IntentGroupId =
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

export const INTENT_GROUPS: IntentGroup[] = [
  { id: "accueil", label: "Accueil & cloture", hint: "Salutations, aide, fin d'appel" },
  { id: "contact", label: "Coordonnees", hint: "Email, rappel, fiches contact" },
  { id: "rdv", label: "Rendez-vous", hint: "Prise, report, annulation" },
  { id: "commercial", label: "Commercial", hint: "Devis, offres, partenariats" },
  { id: "support", label: "Support", hint: "Urgence, SAV, factures" },
  { id: "infos", label: "Infos pratiques", hint: "Horaires, acces, site" },
  { id: "autre", label: "Autres", hint: "Le reste du catalogue" }
];

const TAG_GROUP: Record<string, IntentGroupId> = {
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

/**
 * Assigne un intent a un groupe UI.
 *
 * @param intent Intent.
 * @returns Id groupe.
 */
export function groupIdForIntent(intent: KbIntent): IntentGroupId {
  return TAG_GROUP[intent.tag] || "autre";
}

/**
 * Filtre + regroupe les intents pour l'UI.
 *
 * @param intents Catalogue.
 * @param query Recherche libre.
 * @param groupFilter Groupe ou "all".
 * @returns Map groupe -> intents.
 */
export function groupIntents(
  intents: KbIntent[],
  query: string,
  groupFilter: IntentGroupId | "all"
): Record<IntentGroupId, KbIntent[]> {
  const q = query.trim().toLowerCase();
  const out = Object.fromEntries(INTENT_GROUPS.map((g) => [g.id, [] as KbIntent[]])) as Record<
    IntentGroupId,
    KbIntent[]
  >;

  for (const intent of intents) {
    const gid = groupIdForIntent(intent);
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
    out[gid].push(intent);
  }

  for (const g of INTENT_GROUPS) {
    out[g.id].sort((a, b) => b.priority - a.priority || a.tag.localeCompare(b.tag));
  }
  return out;
}
