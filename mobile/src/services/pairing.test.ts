/** Tests parse QR et claim. */
import { barcodeScanPayload, parsePairUri } from "./pairing";
import { buildApiUrl, claimPairing } from "./api";

describe("pairing", () => {
  it("parse URI vocalguard", () => {
    const parsed = parsePairUri("vocalguard://pair?v=1&host=https://node12.lan&code=AB12CD34");
    expect(parsed?.code).toBe("AB12CD34");
    expect(parsed?.host).toBe("https://node12.lan");
  });

  it("parse URI avec slash apres pair", () => {
    const parsed = parsePairUri("vocalguard://pair/?v=1&host=https://node14.lan&code=ZZ11YY22");
    expect(parsed?.code).toBe("ZZ11YY22");
    expect(parsed?.host).toBe("https://node14.lan");
  });

  it("parse via query string seule", () => {
    const parsed = parsePairUri("?v=1&host=https://test.lan&code=AB12CD34");
    expect(parsed?.host).toBe("https://test.lan");
  });

  it("parse host URL-encode", () => {
    const parsed = parsePairUri(
      "vocalguard://pair?v=1&host=https%3A%2F%2Fvocalguard.danielcraft.fr&code=AB12CD34",
    );
    expect(parsed?.host).toBe("https://vocalguard.danielcraft.fr");
    expect(parsed?.code).toBe("AB12CD34");
  });

  it("parse JSON fallback QR", () => {
    const parsed = parsePairUri('{"v":"1","host":"https://x","code":"ZZ99YY88"}');
    expect(parsed?.code).toBe("ZZ99YY88");
  });

  it("claim API mock", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ token: "t", base_url: "https://x", permissions: {} }),
    }) as jest.Mock;
    const res = await claimPairing("https://x", "AB12CD34");
    expect(buildApiUrl("https://x", "/public/mobile/claim")).toContain("/api/v1/public/mobile/claim");
    expect(res.token).toBe("t");
  });

  it("extrait payload barcode data ou raw", () => {
    expect(barcodeScanPayload({ data: " abc ", raw: "x" })).toBe("abc");
    expect(barcodeScanPayload({ raw: "vocalguard://pair?code=1&host=h" })).toContain("vocalguard");
  });
});
