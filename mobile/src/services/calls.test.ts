/** Tests API appels mobile (detail soft + recording URL). */
import { ApiHttpError } from "./api";
import { callRecordingUrl, fetchCallDetailSoft } from "./calls";

jest.mock("./api", () => {
  const actual = jest.requireActual("./api");
  return {
    ...actual,
    apiGet: jest.fn(),
  };
});

import { apiGet } from "./api";

const config = { baseUrl: "https://vg.test", token: "tok" };

describe("calls service", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("callRecordingUrl pointe vers /public/calls/{id}/recording", () => {
    expect(callRecordingUrl(config, 163)).toBe(
      "https://vg.test/api/v1/public/calls/163/recording",
    );
  });

  it("fetchCallDetailSoft renvoie le detail si OK", async () => {
    (apiGet as jest.Mock).mockResolvedValue({
      id: 163,
      transcription: "Voila, voila, c est Louis.",
    });
    const res = await fetchCallDetailSoft(config, 163);
    expect(res.detail?.id).toBe(163);
    expect(res.error).toBeNull();
  });

  it("fetchCallDetailSoft soft-fail sur 404", async () => {
    (apiGet as jest.Mock).mockRejectedValue(new ApiHttpError(404, "not found"));
    const res = await fetchCallDetailSoft(config, 163);
    expect(res.detail).toBeNull();
    expect(res.error).toMatch(/indisponible/i);
  });

  it("fetchCallDetailSoft soft-fail sur 401", async () => {
    (apiGet as jest.Mock).mockRejectedValue(new ApiHttpError(401, "unauthorized"));
    const res = await fetchCallDetailSoft(config, 1);
    expect(res.detail).toBeNull();
    expect(res.error).toMatch(/401/);
  });
});
