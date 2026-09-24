import {
  formatCallTime,
  formatDetailDateTime,
  formatDuration,
  formatDurationMinSec,
  formatPhone,
  voicemailCallerLabel,
} from "./format";

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

describe("formatDurationMinSec", () => {
  it("retourne vide pour 0", () => {
    expect(formatDurationMinSec(0)).toBe("");
  });

  it("formate comme le web", () => {
    expect(formatDurationMinSec(14)).toBe("0 min 14 s");
    expect(formatDurationMinSec(74)).toBe("1 min 14 s");
  });
});

describe("formatDetailDateTime", () => {
  it("retourne vide si null", () => {
    expect(formatDetailDateTime(null)).toBe("");
  });

  it("formate jour/mois/annee heure", () => {
    const out = formatDetailDateTime("2026-09-23T13:51:00");
    expect(out).toMatch(/23/);
    expect(out).toMatch(/09/);
    expect(out).toMatch(/2026/);
    expect(out).toMatch(/13/);
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
