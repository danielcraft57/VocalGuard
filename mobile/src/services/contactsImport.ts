/**
 * Import contacts telephone vers personnes de confiance.
 */

export interface DeviceContact {
  id?: string;
  name: string;
  phoneNumbers: string[];
}

/**
 * Normalise un numero FR en 0XXXXXXXXX.
 *
 * @param raw Numero brut.
 */
export function normalizeFrPhone(raw: string): string | null {
  let digits = raw.replace(/\D/g, "");
  if (digits.startsWith("0033")) digits = "33" + digits.slice(4);
  if (digits.startsWith("33") && digits.length >= 11) return "0" + digits.slice(2);
  if (digits.startsWith("0") && digits.length >= 10) return digits.slice(0, 11);
  return digits.length >= 10 ? digits : null;
}

/**
 * Prepare le payload import trusted pour l API.
 *
 * @param contacts Contacts selectionnes.
 */
export function buildTrustedImportPayload(contacts: DeviceContact[]): Array<{ name: string; phone_number: string }> {
  const out: Array<{ name: string; phone_number: string }> = [];
  for (const c of contacts) {
    for (const phone of c.phoneNumbers) {
      const normalized = normalizeFrPhone(phone);
      if (normalized) out.push({ name: c.name, phone_number: normalized });
    }
  }
  return out;
}

/**
 * Filtre les contacts ayant au moins un numero valide.
 *
 * @param contacts Liste brute expo-contacts.
 */
export function filterCallableContacts(contacts: DeviceContact[]): DeviceContact[] {
  return contacts.filter((c) => c.phoneNumbers.some((p) => normalizeFrPhone(p) !== null));
}
