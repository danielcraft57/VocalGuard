/** Tests stockage credentials (web fallback). */
import { Platform } from "react-native";
import { BASE_KEY, TOKEN_KEY, clearCredentials, getStoredCredentials, saveCredentials } from "./credentials";

describe("credentials", () => {
  beforeEach(async () => {
    if (Platform.OS === "web" && typeof localStorage !== "undefined") {
      localStorage.removeItem(`vg:${TOKEN_KEY}`);
      localStorage.removeItem(`vg:${BASE_KEY}`);
    }
  });

  it("save puis read", async () => {
    await saveCredentials("tok123", "https://example.test");
    const creds = await getStoredCredentials();
    expect(creds.token).toBe("tok123");
    expect(creds.baseUrl).toBe("https://example.test");
  });

  it("clear efface tout", async () => {
    await saveCredentials("tok", "https://x");
    await clearCredentials();
    const creds = await getStoredCredentials();
    expect(creds.token).toBeNull();
    expect(creds.baseUrl).toBeNull();
  });
});
