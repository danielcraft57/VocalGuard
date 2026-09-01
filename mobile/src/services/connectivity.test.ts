/** Tests connectivite LAN. */
import { pingHealth, resolveConnectivityState } from "./connectivity";

describe("connectivity", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("detecte online si health OK", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({ ok: true });
    await expect(pingHealth("https://node12.lan")).resolves.toBe(true);
  });

  it("detecte offline si fetch echoue", async () => {
    (global.fetch as jest.Mock).mockRejectedValue(new Error("network"));
    await expect(pingHealth("https://node12.lan")).resolves.toBe(false);
  });

  it("retourne syncing si demande", async () => {
    await expect(resolveConnectivityState("https://x", true)).resolves.toBe("syncing");
  });
});
