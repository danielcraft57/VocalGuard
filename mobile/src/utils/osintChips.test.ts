/** Tests chips OSINT (agencement detail aligne web). */
import { buildOsintChips } from "./osintChips";

describe("buildOsintChips", () => {
  it("retourne [] sans profil", () => {
    expect(buildOsintChips(null)).toEqual([]);
  });

  it("construit recommendation / operator / lieu", () => {
    const chips = buildOsintChips({
      recommendation: "review",
      reputation: "neutral",
      operator: "Orange",
      city: "France entiere (mobile)",
    });
    const labels = chips.map((c) => c.label);
    expect(labels).toContain("review / neutral");
    expect(labels).toContain("Orange");
    expect(labels).toContain("France entiere (mobile)");
  });

  it("ajoute Spam / Arnaque", () => {
    const chips = buildOsintChips({
      reputation: "low",
      is_spam: true,
      is_scam: true,
    });
    const labels = chips.map((c) => c.label);
    expect(labels).toContain("Spam");
    expect(labels).toContain("Arnaque");
  });
});
