/** Tests garde de navigation auth. */
import { resolveAuthRedirect } from "./authNav";

describe("resolveAuthRedirect", () => {
  it("envoie vers onboarding sans token", () => {
    expect(resolveAuthRedirect(null, undefined)).toBe("/onboarding");
    expect(resolveAuthRedirect(null, "(tabs)")).toBe("/onboarding");
  });

  it("laisse l onboarding si pas de token", () => {
    expect(resolveAuthRedirect(null, "onboarding")).toBeNull();
  });

  it("sort de l onboarding si token present", () => {
    expect(resolveAuthRedirect("tok", "onboarding")).toBe("/(tabs)/calls");
  });

  it("envoie l index vers les tabs si token present", () => {
    expect(resolveAuthRedirect("tok", undefined)).toBe("/(tabs)/calls");
  });

  it("ne boucle pas une fois sur les tabs", () => {
    expect(resolveAuthRedirect("tok", "(tabs)")).toBeNull();
  });
});
