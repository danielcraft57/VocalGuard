import { fetchTrustedList, removeTrustedContact } from "./trusted";
import { apiGet } from "./api";

jest.mock("./api", () => ({
  apiGet: jest.fn(),
  apiDelete: jest.fn(),
}));

const { apiDelete } = jest.requireMock("./api") as { apiDelete: jest.Mock };

describe("trusted", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("parse la liste trusted", async () => {
    (apiGet as jest.Mock).mockResolvedValue({
      trusted: [{ phone_number: "0612345678", name: "Alice" }],
    });
    const rows = await fetchTrustedList({ baseUrl: "https://t", token: "x" });
    expect(rows).toEqual([{ phone_number: "0612345678", name: "Alice", updated_at: null }]);
  });

  it("supprime un contact", async () => {
    apiDelete.mockResolvedValue({ ok: true });
    await removeTrustedContact({ baseUrl: "https://t", token: "x" }, "0612345678");
    expect(apiDelete).toHaveBeenCalledWith(
      { baseUrl: "https://t", token: "x" },
      "/public/trusted/0612345678",
    );
  });
});
