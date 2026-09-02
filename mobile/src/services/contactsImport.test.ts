/** Tests import contacts confiance. */
import { buildTrustedImportPayload, contactKey, filterCallableContacts, normalizeFrPhone } from "./contactsImport";

describe("contactsImport", () => {
  it("normalise +33 et 06", () => {
    expect(normalizeFrPhone("+33 6 12 34 56 78")).toBe("0612345678");
    expect(normalizeFrPhone("06.12.34.56.78")).toBe("0612345678");
  });

  it("filtre contacts sans numero valide", () => {
    const rows = filterCallableContacts([
      { name: "A", phoneNumbers: ["0612345678"] },
      { name: "B", phoneNumbers: ["123"] },
    ]);
    expect(rows).toHaveLength(1);
  });

  it("prepare payload import batch", () => {
    const payload = buildTrustedImportPayload([
      { name: "Alice", phoneNumbers: ["06 12 34 56 78", "+33 7 00 00 00 00"] },
    ]);
    expect(payload.length).toBeGreaterThanOrEqual(1);
    expect(payload[0].phone_number).toMatch(/^0/);
  });

  it("genere une cle stable sans id", () => {
    expect(contactKey({ name: "Bob", phoneNumbers: ["0612345678"] })).toBe("Bob:0612345678");
  });
});
