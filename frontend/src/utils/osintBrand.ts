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
  carrier?: string | null;
  company_name?: string | null;
  name?: string | null;
};

type BrandDef = {
  id: string;
  match: RegExp;
  /** Sous-chaines ASCII simples (filet Hermes / Android). */
  needles: string[];
  short: string;
  bg: string;
  fg: string;
  title: string;
};

function brand(
  id: string,
  match: RegExp,
  needles: string[],
  short: string,
  bg: string,
  fg: string,
  title: string,
): BrandDef {
  return { id, match, needles, short, bg, fg, title };
}

/**
 * Catalogue marques : interim / RH d abord, puis operateurs telecom FR.
 * Ordre = priorite de match (plus specifique en premier).
 */
const BRANDS: BrandDef[] = [
  // --- Agences d interim / RH ---
  brand("manpower", /\bmanpower(?:group)?\b/i, ["manpower"], "MP", "#0072CE", "#ffffff", "Manpower"),
  brand("adecco", /\badecco\b/i, ["adecco"], "AD", "#EF3E33", "#ffffff", "Adecco"),
  brand("randstad", /\brandstad\b|\bvedior\b/i, ["randstad", "vedior"], "RS", "#2175D9", "#ffffff", "Randstad"),
  brand("synergie", /\bsynergie\b/i, ["synergie"], "SY", "#E30613", "#ffffff", "Synergie"),
  brand("crit", /\bcrit(?:\s|$)|groupe\s+crit\b/i, ["groupe crit", "crit "], "CR", "#009639", "#ffffff", "Crit"),
  brand("proman", /\bproman\b/i, ["proman"], "PR", "#F7A800", "#1a1a1a", "Proman"),
  brand("expectra", /\bexpectra\b/i, ["expectra"], "EX", "#E30613", "#ffffff", "Expectra"),
  brand("page", /\bmichael\s*page\b|\bpage\s*personnel\b|\bpagegroup\b/i, ["michael page", "page personnel", "pagegroup"], "PG", "#1D1D1B", "#ffffff", "PageGroup"),
  brand("start_people", /\bstart\s*people\b/i, ["start people"], "SP", "#00A3E0", "#ffffff", "Start People"),
  brand("temporis", /\btemporis\b/i, ["temporis"], "TE", "#6B2D8B", "#ffffff", "Temporis"),
  brand("actual", /\b(?:groupe\s+)?actual\b|\bactual\s+group\b/i, ["groupe actual", "actual group"], "AC", "#FF6B00", "#ffffff", "Actual"),
  brand("kelly", /\bkelly(?:\s+services)?\b/i, ["kelly"], "KE", "#6B2C91", "#ffffff", "Kelly"),
  brand("hays", /\bhays\b/i, ["hays"], "HY", "#D50032", "#ffffff", "Hays"),
  brand("robert_half", /\brobert\s*half\b/i, ["robert half"], "RH", "#C8102E", "#ffffff", "Robert Half"),
  brand("adequat", /\bad[eé]quat\b/i, ["adequat", "adéquat"], "AQ", "#00AEEF", "#ffffff", "Adequat"),
  brand("aquila", /\baquila(?:\s*rh)?\b/i, ["aquila"], "AR", "#003366", "#ffffff", "Aquila RH"),
  brand("interaction", /\binteraction(?:\s+interim)?\b/i, ["interaction"], "IN", "#E31C23", "#ffffff", "Interaction"),
  brand("partnaire", /\bpartnaire\b/i, ["partnaire"], "PT", "#00A651", "#ffffff", "Partnaire"),
  brand("gojob", /\bgo\s*job\b|\bgojob\b/i, ["gojob", "go job"], "GJ", "#5B2EFF", "#ffffff", "Gojob"),
  brand("staffmatch", /\bstaff\s*match\b|\bstaffmatch\b/i, ["staffmatch", "staff match"], "SM", "#0D9488", "#ffffff", "Staffmatch"),
  brand("mistertemp", /\bmister\s*temp'?s?\b|\bmistertemp\b/i, ["mistertemp", "mister temp"], "MT", "#FF5A00", "#ffffff", "MisterTemp"),
  brand("unique", /\bunique\s+(?:interim|rh|personnels?)\b/i, ["unique interim", "unique rh"], "UQ", "#E4002B", "#ffffff", "Unique"),
  brand("flexemploi", /\bflex\s*emploi\b|\bflexemploi\b/i, ["flex emploi", "flexemploi"], "FL", "#00857C", "#ffffff", "Flex Emploi"),
  brand("eras", /\beras(?:\s+groupe)?\b/i, ["eras"], "ER", "#1B4F72", "#ffffff", "Eras"),
  brand("lynx", /\blynx\s*(?:rh|interim)?\b/i, ["lynx"], "LX", "#111827", "#ffffff", "Lynx RH"),
  brand("taskforce", /\btask\s*force\b/i, ["task force"], "TF", "#DC2626", "#ffffff", "Task Force"),
  brand("samsic", /\bsamsic\b/i, ["samsic"], "SA", "#00A651", "#ffffff", "Samsic"),

  // --- Operateurs telecom FR ---
  brand("sosh", /\bsosh\b/i, ["sosh"], "SO", "#FF7900", "#ffffff", "Sosh"),
  brand("orange", /\borange\b/i, ["orange"], "O", "#FF7900", "#ffffff", "Orange"),
  brand("red", /\bred\s*(?:by\s*)?sfr\b/i, ["red by sfr", "red sfr"], "RED", "#E2001A", "#ffffff", "RED by SFR"),
  brand("sfr", /\bsfr\b|\bnumericable\b/i, ["sfr", "numericable"], "SFR", "#E2001A", "#ffffff", "SFR"),
  brand("free", /\bfree(?:\s*mobile)?\b/i, ["free"], "Free", "#CD1E5C", "#ffffff", "Free"),
  brand("bouygues", /\bbouygues(?:\s*telecom)?\b|\bb\s*&\s*you\b|\bbandyou\b/i, ["bouygues", "b&you", "bandyou"], "BY", "#009DCC", "#ffffff", "Bouygues"),
  brand("coriolis", /\bcoriolis\b/i, ["coriolis"], "CO", "#6C2C91", "#ffffff", "Coriolis"),
  brand("prixtel", /\bprixtel\b/i, ["prixtel"], "PX", "#00ADEF", "#ffffff", "Prixtel"),
  brand("laposte", /\bla\s*poste\s*mobile\b/i, ["la poste mobile"], "LP", "#FFCC00", "#1a1a1a", "La Poste Mobile"),
  brand("syma", /\bsyma\b/i, ["syma"], "SY", "#E6007E", "#ffffff", "Syma"),
  brand("lebara", /\blebara\b/i, ["lebara"], "LB", "#00A651", "#ffffff", "Lebara"),
  brand("lycamobile", /\blyca(?:mobile)?\b/i, ["lycamobile", "lyca"], "LY", "#6B2D8B", "#ffffff", "Lycamobile"),
  brand("nrj", /\bnrj\s*mobile\b/i, ["nrj mobile"], "NRJ", "#E30613", "#ffffff", "NRJ Mobile"),
  brand("auchan", /\bauchan\s*(?:telecom|mobile)?\b/i, ["auchan"], "AU", "#E4002B", "#ffffff", "Auchan Telecom"),
  brand("virgin", /\bvirgin(?:\s*mobile)?\b/i, ["virgin"], "VM", "#E10A0A", "#ffffff", "Virgin Mobile"),
  brand("youprice", /\byouprice\b/i, ["youprice"], "YP", "#00B5E2", "#ffffff", "Youprice"),
  brand("reglo", /\breglo(?:\s*mobile)?\b|\bcarrefour\s*mobile\b/i, ["reglo", "carrefour mobile"], "RG", "#004E98", "#ffffff", "Reglo Mobile"),
  brand("cic", /\bcic\s*mobile\b/i, ["cic mobile"], "CIC", "#009639", "#ffffff", "CIC Mobile"),
  brand("credit_mutuel", /\bcr[eé]dit\s*mutuel\s*mobile\b/i, ["credit mutuel mobile", "crédit mutuel mobile"], "CM", "#E30613", "#ffffff", "Credit Mutuel Mobile"),
];

/**
 * Teste si le texte matche une marque (regex + includes ASCII).
 *
 * @param text Texte source.
 * @param def Definition marque.
 */
function textMatchesBrand(text: string, def: BrandDef): boolean {
  if (!text) return false;
  if (def.match.test(text)) return true;
  const lower = text.toLowerCase();
  return def.needles.some((n) => lower.includes(n));
}

/**
 * Initials courtes pour pastille generique.
 *
 * @param label Nom operateur / entreprise.
 * @returns 1 a 3 caracteres.
 */
function shortFromLabel(label: string): string {
  const cleaned = label.replace(/[^a-zA-Z0-9àâäéèêëïîôùûüçÀÂÄÉÈÊËÏÎÔÙÛÜÇ&\s]/g, " ").trim();
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  const one = parts[0] || label;
  return one.slice(0, Math.min(3, one.length)).toUpperCase();
}

/**
 * Detecte une marque connue depuis le profil OSINT.
 * Priorite : entreprise (interim, etc.) puis operateur telecom.
 * Sinon pastille generique (initiales) si on a un nom / operateur.
 *
 * @param osint Profil leger ou null.
 * @returns Visuel marque ou null si aucune info.
 * @example
 * resolveOsintBrand({ operator: "Orange" })?.id // "orange"
 */
export function resolveOsintBrand(osint?: OsintBrandSource | null): OsintBrandVisual | null {
  if (!osint) return null;
  const company = `${osint.company_name || ""} ${osint.name || ""}`.trim();
  const operator = `${osint.operator || ""} ${osint.carrier || ""}`.trim();
  if (!company && !operator) return null;

  for (const def of BRANDS) {
    if (company && textMatchesBrand(company, def)) {
      return { id: def.id, short: def.short, bg: def.bg, fg: def.fg, title: def.title };
    }
  }
  for (const def of BRANDS) {
    if (operator && textMatchesBrand(operator, def)) {
      return { id: def.id, short: def.short, bg: def.bg, fg: def.fg, title: def.title };
    }
  }

  const label = company || operator;
  return {
    id: "generic",
    short: shortFromLabel(label),
    bg: "#475569",
    fg: "#ffffff",
    title: label,
  };
}

