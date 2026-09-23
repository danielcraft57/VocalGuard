/**
 * Resolution d une marque OSINT connue (operateur / entreprise / interim)
 * pour pastille sous l icone entrant/sortant.
 */

export type OsintBrandVisual = {
  /** Identifiant machine. */
  id: string;
  /** Texte court dans la pastille. */
  short: string;
  /** Couleur de fond. */
  bg: string;
  /** Couleur du texte. */
  fg: string;
  /** Libelle accessibilite / tooltip. */
  title: string;
};

type OsintBrandSource = {
  operator?: string | null;
  company_name?: string | null;
  name?: string | null;
};

type BrandDef = {
  id: string;
  match: RegExp;
  short: string;
  bg: string;
  fg: string;
  title: string;
};

/**
 * Catalogue marques : interim / RH d abord, puis operateurs telecom FR.
 * Ordre = priorite de match (plus specifique en premier).
 */
const BRANDS: BrandDef[] = [
  // --- Agences d interim / RH ---
  { id: "manpower", match: /\bmanpower(?:group)?\b/i, short: "MP", bg: "#0072CE", fg: "#fff", title: "Manpower" },
  { id: "adecco", match: /\badecco\b/i, short: "AD", bg: "#EF3E33", fg: "#fff", title: "Adecco" },
  { id: "randstad", match: /\brandstad\b|\bvedior\b/i, short: "RS", bg: "#2175D9", fg: "#fff", title: "Randstad" },
  { id: "synergie", match: /\bsynergie\b/i, short: "SY", bg: "#E30613", fg: "#fff", title: "Synergie" },
  { id: "crit", match: /\bcrit(?:\s|$)|groupe\s+crit\b/i, short: "CR", bg: "#009639", fg: "#fff", title: "Crit" },
  { id: "proman", match: /\bproman\b/i, short: "PR", bg: "#F7A800", fg: "#1a1a1a", title: "Proman" },
  { id: "expectra", match: /\bexpectra\b/i, short: "EX", bg: "#E30613", fg: "#fff", title: "Expectra" },
  { id: "page", match: /\bmichael\s*page\b|\bpage\s*personnel\b|\bpagegroup\b/i, short: "PG", bg: "#1D1D1B", fg: "#fff", title: "PageGroup" },
  { id: "start_people", match: /\bstart\s*people\b/i, short: "SP", bg: "#00A3E0", fg: "#fff", title: "Start People" },
  { id: "temporis", match: /\btemporis\b/i, short: "TE", bg: "#6B2D8B", fg: "#fff", title: "Temporis" },
  { id: "actual", match: /\b(?:groupe\s+)?actual\b|\bactual\s+group\b/i, short: "AC", bg: "#FF6B00", fg: "#fff", title: "Actual" },
  { id: "kelly", match: /\bkelly(?:\s+services)?\b/i, short: "KE", bg: "#6B2C91", fg: "#fff", title: "Kelly" },
  { id: "hays", match: /\bhays\b/i, short: "HY", bg: "#D50032", fg: "#fff", title: "Hays" },
  { id: "robert_half", match: /\brobert\s*half\b/i, short: "RH", bg: "#C8102E", fg: "#fff", title: "Robert Half" },
  { id: "adequat", match: /\bad[eé]quat\b/i, short: "AQ", bg: "#00AEEF", fg: "#fff", title: "Adequat" },
  { id: "aquila", match: /\baquila(?:\s*rh)?\b/i, short: "AQ", bg: "#003366", fg: "#fff", title: "Aquila RH" },
  { id: "interaction", match: /\binteraction(?:\s+interim)?\b/i, short: "IN", bg: "#E31C23", fg: "#fff", title: "Interaction" },
  { id: "partnaire", match: /\bpartnaire\b/i, short: "PT", bg: "#00A651", fg: "#fff", title: "Partnaire" },
  { id: "gojob", match: /\bgo\s*job\b|\bgojob\b/i, short: "GJ", bg: "#5B2EFF", fg: "#fff", title: "Gojob" },
  { id: "staffmatch", match: /\bstaff\s*match\b|\bstaffmatch\b/i, short: "SM", bg: "#0D9488", fg: "#fff", title: "Staffmatch" },
  { id: "mistertemp", match: /\bmister\s*temp'?s?\b|\bmistertemp\b/i, short: "MT", bg: "#FF5A00", fg: "#fff", title: "MisterTemp" },
  { id: "unique", match: /\bunique\s+(?:interim|rh|personnels?)\b/i, short: "UQ", bg: "#E4002B", fg: "#fff", title: "Unique" },
  { id: "flexemploi", match: /\bflex\s*emploi\b|\bflexemploi\b/i, short: "FL", bg: "#00857C", fg: "#fff", title: "Flex Emploi" },
  { id: "eras", match: /\beras(?:\s+groupe)?\b/i, short: "ER", bg: "#1B4F72", fg: "#fff", title: "Eras" },
  { id: "lynx", match: /\blynx\s*(?:rh|interim)?\b/i, short: "LX", bg: "#111827", fg: "#fff", title: "Lynx RH" },
  { id: "taskforce", match: /\btask\s*force\b/i, short: "TF", bg: "#DC2626", fg: "#fff", title: "Task Force" },
  { id: "samsic", match: /\bsamsic\b/i, short: "SA", bg: "#00A651", fg: "#fff", title: "Samsic" },

  // --- Operateurs telecom FR ---
  { id: "sosh", match: /\bsosh\b/i, short: "SO", bg: "#FF7900", fg: "#fff", title: "Sosh" },
  { id: "orange", match: /\borange\b/i, short: "O", bg: "#FF7900", fg: "#fff", title: "Orange" },
  { id: "red", match: /\bred\s*(?:by\s*)?sfr\b|\bred\b(?=.*sfr)/i, short: "RED", bg: "#E2001A", fg: "#fff", title: "RED by SFR" },
  { id: "sfr", match: /\bsfr\b|\bnumericable\b/i, short: "SFR", bg: "#E2001A", fg: "#fff", title: "SFR" },
  { id: "free", match: /\bfree(?:\s*mobile)?\b/i, short: "Free", bg: "#CD1E5C", fg: "#fff", title: "Free" },
  { id: "bouygues", match: /\bbouygues(?:\s*telecom)?\b|\bb\s*&\s*you\b|\bbandyou\b/i, short: "BY", bg: "#009DCC", fg: "#fff", title: "Bouygues" },
  { id: "coriolis", match: /\bcoriolis\b/i, short: "CO", bg: "#6C2C91", fg: "#fff", title: "Coriolis" },
  { id: "prixtel", match: /\bprixtel\b/i, short: "PX", bg: "#00ADEF", fg: "#fff", title: "Prixtel" },
  { id: "laposte", match: /\bla\s*poste\s*mobile\b|\blpm\b/i, short: "LP", bg: "#FFCC00", fg: "#1a1a1a", title: "La Poste Mobile" },
  { id: "syma", match: /\bsyma\b/i, short: "SY", bg: "#E6007E", fg: "#fff", title: "Syma" },
  { id: "lebara", match: /\blebara\b/i, short: "LB", bg: "#00A651", fg: "#fff", title: "Lebara" },
  { id: "lycamobile", match: /\blyca(?:mobile)?\b/i, short: "LY", bg: "#6B2D8B", fg: "#fff", title: "Lycamobile" },
  { id: "nrj", match: /\bnrj\s*mobile\b/i, short: "NRJ", bg: "#E30613", fg: "#fff", title: "NRJ Mobile" },
  { id: "auchan", match: /\bauchan\s*(?:telecom|mobile)?\b/i, short: "AU", bg: "#E4002B", fg: "#fff", title: "Auchan Telecom" },
  { id: "virgin", match: /\bvirgin(?:\s*mobile)?\b/i, short: "VM", bg: "#E10A0A", fg: "#fff", title: "Virgin Mobile" },
  { id: "youprice", match: /\byouprice\b/i, short: "YP", bg: "#00B5E2", fg: "#fff", title: "Youprice" },
  { id: "reglo", match: /\breglo(?:\s*mobile)?\b|\bcarrefour\s*mobile\b/i, short: "RG", bg: "#004E98", fg: "#fff", title: "Reglo Mobile" },
  { id: "cic", match: /\bcic\s*mobile\b/i, short: "CIC", bg: "#009639", fg: "#fff", title: "CIC Mobile" },
  { id: "credit_mutuel", match: /\bcr[eé]dit\s*mutuel\s*mobile\b/i, short: "CM", bg: "#E30613", fg: "#fff", title: "Credit Mutuel Mobile" },
];

/**
 * Detecte une marque connue depuis le profil OSINT.
 * Priorite : entreprise (interim, etc.) puis operateur telecom.
 *
 * @param osint Profil leger ou null.
 * @returns Visuel marque ou null si aucune info reconnue.
 * @example
 * resolveOsintBrand({ operator: "Orange" })?.id // "orange"
 */
export function resolveOsintBrand(osint?: OsintBrandSource | null): OsintBrandVisual | null {
  if (!osint) return null;
  const company = `${osint.company_name || ""} ${osint.name || ""}`.trim();
  const operator = (osint.operator || "").trim();
  for (const brand of BRANDS) {
    if (company && brand.match.test(company)) {
      return {
        id: brand.id,
        short: brand.short,
        bg: brand.bg,
        fg: brand.fg,
        title: brand.title,
      };
    }
  }
  for (const brand of BRANDS) {
    if (operator && brand.match.test(operator)) {
      return {
        id: brand.id,
        short: brand.short,
        bg: brand.bg,
        fg: brand.fg,
        title: brand.title,
      };
    }
  }
  return null;
}
