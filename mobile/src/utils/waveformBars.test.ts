/** Tests forme d onde deterministe pour scrubber. */
import { buildWaveformBars, waveformIndexAt } from "./waveformBars";

describe("waveformBars", () => {
  it("genere le meme profil pour le meme seed", () => {
    expect(buildWaveformBars(163, 24)).toEqual(buildWaveformBars(163, 24));
  });

  it("produit des hauteurs entre 0.18 et 1", () => {
    const bars = buildWaveformBars(42, 40);
    expect(bars).toHaveLength(40);
    for (const h of bars) {
      expect(h).toBeGreaterThanOrEqual(0.18);
      expect(h).toBeLessThanOrEqual(1);
    }
  });

  it("waveformIndexAt borne le ratio", () => {
    expect(waveformIndexAt(0, 48)).toBe(0);
    expect(waveformIndexAt(1, 48)).toBe(47);
    expect(waveformIndexAt(0.5, 10)).toBe(5);
  });
});
