/**
 * Tests service appairage mobile.
 */

import { createPairingSession, testMobilePing } from "./mobilePairingApi";
import { getApiBaseUrl } from "./httpClient";

jest.mock("./httpClient", () => ({
  getApiBaseUrl: jest.fn(() => "http://localhost:8000/api/v1"),
}));

describe("mobilePairingApi", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn();
  });

  it("appelle POST /tokens/pairing-sessions", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        pairing_id: 2,
        code: "XYZ12345",
        expires_at: "2026-01-01T00:00:00Z",
        qr_uri: "vocalguard://pair?code=XYZ12345",
      }),
    });

    const result = await createPairingSession({
      base_url: "https://vocalguard.test",
      create_token_if_missing: true,
    });

    expect(getApiBaseUrl).toHaveBeenCalled();
    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/tokens/pairing-sessions",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(result.code).toBe("XYZ12345");
  });

  it("appelle GET /public/mobile/ping avec Bearer", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ok: true, api_ok: true, ws_ok: true, modem_ok: true, permissions: {} }),
    });

    const ping = await testMobilePing("token-secret");
    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/public/mobile/ping",
      expect.objectContaining({
        headers: { Authorization: "Bearer token-secret" },
      }),
    );
    expect(ping.ok).toBe(true);
  });
});
