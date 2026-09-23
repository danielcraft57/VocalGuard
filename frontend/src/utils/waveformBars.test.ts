/** Tests forme d onde (scrubber Material). */
import { buildWaveformBars, waveformIndexAt } from "./waveformBars";

describe("waveformBars", () => {
  it("produit N hauteurs stables pour un seed", () => {
    const a = buildWaveformBars(163, 32);
    const b = buildWaveformBars(163, 32);
    expect(a).toHaveLength(32);
    expect(a).toEqual(b);
    expect(Math.min(...a)).toBeGreaterThanOrEqual(0.18);
    expect(Math.max(...a)).toBeLessThanOrEqual(1);
  });

  it("waveformIndexAt borne le progress", () => {
    expect(waveformIndexAt(0, 10)).toBe(0);
    expect(waveformIndexAt(1, 10)).toBe(9);
    expect(waveformIndexAt(0.5, 10)).toBe(5);
  });
});
