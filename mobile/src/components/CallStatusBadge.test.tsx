import { resolveCallStatusKind } from "./CallStatusBadge";

describe("resolveCallStatusKind", () => {
  it("mappe missed", () => {
    expect(resolveCallStatusKind("missed")).toBe("missed");
  });

  it("mappe blocked", () => {
    expect(resolveCallStatusKind("blocked")).toBe("blocked");
  });

  it("mappe answered et completed", () => {
    expect(resolveCallStatusKind("answered")).toBe("answered");
    expect(resolveCallStatusKind("completed")).toBe("answered");
  });

  it("retourne other pour statut inconnu", () => {
    expect(resolveCallStatusKind("foo")).toBe("other");
  });
});
