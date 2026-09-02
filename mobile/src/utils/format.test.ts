import { formatCallTime, formatDuration, formatPhone, voicemailCallerLabel } from "./format";

describe("formatCallTime", () => {
  it("retourne une chaine vide si null", () => {
    expect(formatCallTime(null)).toBe("");
  });

  it("formate une date valide", () => {
    const iso = "2026-09-01T14:30:00.000Z";
    const out = formatCallTime(iso);
    expect(out.length).toBeGreaterThan(0);
  });
});

describe("formatDuration", () => {
  it("retourne vide pour 0", () => {
    expect(formatDuration(0)).toBe("");
  });

  it("formate mm:ss", () => {
    expect(formatDuration(125)).toBe("2:05");
  });
});

describe("formatPhone", () => {
  it("groupe un numero FR 10 chiffres", () => {
    expect(formatPhone("0612345678")).toBe("06 12 34 56 78");
  });

  it("laisse les numeros non standards", () => {
    expect(formatPhone("+33123")).toBe("+33123");
  });
});

describe("voicemailCallerLabel", () => {
  it("affiche nom et numero", () => {
    expect(voicemailCallerLabel("Jean", "0612345678")).toEqual({
      title: "Jean",
      subtitle: "06 12 34 56 78",
    });
  });

  it("affiche Inconnu si vide", () => {
    expect(voicemailCallerLabel(null, "")).toEqual({ title: "Inconnu", subtitle: null });
  });
});
