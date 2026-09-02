/** Tests session expiree. */
import { invalidateMobileSession, setSessionCleanupHandler, setSessionExpiredHandler } from "./session";
import { clearCredentials } from "./credentials";

jest.mock("./credentials", () => ({
  clearCredentials: jest.fn(),
}));

describe("session", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("appelle cleanup et redirect handler", async () => {
    const cleanup = jest.fn();
    const expired = jest.fn();
    setSessionCleanupHandler(cleanup);
    setSessionExpiredHandler(expired);

    await invalidateMobileSession("test 401");

    expect(cleanup).toHaveBeenCalled();
    expect(clearCredentials).toHaveBeenCalled();
    expect(expired).toHaveBeenCalled();
  });
});
