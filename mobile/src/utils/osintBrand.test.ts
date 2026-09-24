/** Tests resolution marque OSINT. */
import { resolveOsintBrand } from "./osintBrand";

describe("resolveOsintBrand", () => {
  it("retourne null sans OSINT", () => {
    expect(resolveOsintBrand(null)).toBeNull();
    expect(resolveOsintBrand({})).toBeNull();
  });

  it("detecte les operateurs principaux", () => {
    expect(resolveOsintBrand({ operator: "Orange" })?.id).toBe("orange");
    expect(resolveOsintBrand({ operator: "SFR" })?.id).toBe("sfr");
    expect(resolveOsintBrand({ operator: "Free Mobile" })?.id).toBe("free");
    expect(resolveOsintBrand({ operator: "Bouygues Telecom" })?.id).toBe("bouygues");
  });

  it("detecte les interim et services", () => {
    expect(resolveOsintBrand({ company_name: "Manpower France" })?.id).toBe("manpower");
    expect(resolveOsintBrand({ company_name: "Adecco" })?.id).toBe("adecco");
    expect(resolveOsintBrand({ company_name: "Randstad" })?.id).toBe("randstad");
    expect(resolveOsintBrand({ name: "SAMSIC FACILITY" })?.id).toBe("samsic");
    expect(resolveOsintBrand({ company_name: "Proman Interim" })?.id).toBe("proman");
  });

  it("priorise l entreprise sur l operateur", () => {
    expect(
      resolveOsintBrand({ company_name: "Manpower", operator: "Orange" })?.id,
    ).toBe("manpower");
  });
});
