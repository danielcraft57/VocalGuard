import { routeParam } from "./nav";

describe("nav", () => {
  it("normalise un param tableau", () => {
    expect(routeParam(["0612345678", "ignored"])).toBe("0612345678");
  });

  it("retourne une chaine vide si absent", () => {
    expect(routeParam(undefined)).toBe("");
  });
});
