/** Tests bornage seek audio (evite NaN sur HTMLMediaElement.currentTime). */
import { clampSeekSeconds } from "./seekClamp";

describe("clampSeekSeconds", () => {
  it("rejette NaN et Infinity", () => {
    expect(clampSeekSeconds(Number.NaN)).toBeNull();
    expect(clampSeekSeconds(Number.POSITIVE_INFINITY)).toBeNull();
    expect(clampSeekSeconds(Number.NEGATIVE_INFINITY)).toBeNull();
  });

  it("borne a 0 et a la duree", () => {
    expect(clampSeekSeconds(-3, 14)).toBe(0);
    expect(clampSeekSeconds(20, 14)).toBe(14);
    expect(clampSeekSeconds(7.5, 14)).toBe(7.5);
  });

  it("sans duree conserve la valeur positive", () => {
    expect(clampSeekSeconds(3.2)).toBe(3.2);
  });
});
