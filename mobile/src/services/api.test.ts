/** Tests client REST mobile. */
import { apiGet, ApiHttpError, buildApiUrl, isApiUnauthorized, pingMobile } from "./api";
import { invalidateMobileSession } from "./session";

jest.mock("./session", () => ({
  invalidateMobileSession: jest.fn(),
}));

describe("api", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("ajoute Bearer sur GET", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    await apiGet({ baseUrl: "https://test", token: "secret" }, "/public/mobile/ping");
    expect(global.fetch).toHaveBeenCalledWith(
      buildApiUrl("https://test", "/public/mobile/ping"),
      expect.objectContaining({ headers: { Authorization: "Bearer secret" } }),
    );
  });

  it("remonte erreur 401", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({ ok: false, status: 401 });
    await expect(pingMobile({ baseUrl: "https://t", token: "x" })).rejects.toThrow(ApiHttpError);
    expect(invalidateMobileSession).toHaveBeenCalled();
    expect(isApiUnauthorized(new ApiHttpError(401, "x"))).toBe(true);
  });
});
