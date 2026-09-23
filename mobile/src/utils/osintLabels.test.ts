/** Tests labels OSINT. */
import {
  formatOsintMeta,
  getReputationCategory,
  getReputationColor,
  getReputationLabel,
} from "./osintLabels";

describe("osintLabels", () => {
  it("categorise high / low / spam", () => {
    expect(getReputationCategory({ reputation: "high" })).toBe("good");
    expect(getReputationCategory({ reputation: "low" })).toBe("bad");
    expect(getReputationCategory({ reputation: "neutral", is_spam: true })).toBe("bad");
    expect(getReputationCategory(null)).toBe("unknown");
  });

  it("libelle FR et couleurs", () => {
    expect(getReputationLabel({ reputation: "high" })).toBe("Bonne");
    expect(getReputationLabel({ reputation: "low" })).toBe("Risque");
    expect(getReputationColor("good").fg).toBe("#22c55e");
    expect(getReputationColor("bad").fg).toBe("#ef4444");
  });

  it("formatOsintMeta assemble entreprise et lieu", () => {
    expect(
      formatOsintMeta({
        company_name: "Orange",
        operator: "Orange",
        city: "Paris",
      }),
    ).toContain("Orange");
    expect(formatOsintMeta(null)).toBeNull();
  });
});
