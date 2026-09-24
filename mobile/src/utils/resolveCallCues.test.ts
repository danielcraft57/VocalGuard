/** Tests resolution cues karaoke (cache local + detail API). */
import { resolveCallCues } from "./resolveCallCues";
import type { CallRow } from "../db/schema";

function baseCall(over: Partial<CallRow> = {}): CallRow {
  return {
    id: 163,
    phone_number: "0780833873",
    caller_name: null,
    status: "answered",
    call_time: "2026-09-23T13:51:00",
    duration: 14,
    synced_at: null,
    transcription: null,
    transcription_cues_json: null,
    no_message: 0,
    osint_json: null,
    ...over,
  };
}

describe("resolveCallCues", () => {
  it("retourne [] si no_message", () => {
    expect(resolveCallCues(baseCall({ no_message: 1 }), null)).toEqual([]);
    expect(
      resolveCallCues(baseCall(), { no_message: true, transcription: "x" }),
    ).toEqual([]);
  });

  it("utilise la transcription locale si le detail API est absent", () => {
    const cues = resolveCallCues(
      baseCall({ transcription: "Voila, voila, c est Louis." }),
      null,
    );
    expect(cues.length).toBeGreaterThan(0);
    const words = cues.flatMap((c) => c.words.map((w) => w.text));
    expect(words.join(" ")).toContain("Voila");
    expect(words.join(" ")).toContain("Louis");
  });

  it("prefereles cues du detail API", () => {
    const cues = resolveCallCues(
      baseCall({ transcription: "texte local ignore" }),
      {
        transcription: "Bonjour",
        duration: 2,
        extra_data: {
          transcription_cues: [
            {
              start: 0,
              end: 1.2,
              words: [
                { text: "Bonjour", start: 0, end: 1.2 },
              ],
            },
          ],
        },
      },
    );
    expect(cues).toHaveLength(1);
    expect(cues[0].words[0].text).toBe("Bonjour");
  });

  it("utilise les cues JSON locaux si pas de detail", () => {
    const cues = resolveCallCues(
      baseCall({
        transcription_cues_json: JSON.stringify([
          {
            start: 0,
            end: 2,
            words: [
              { text: "Salut", start: 0, end: 1 },
              { text: "toi", start: 1, end: 2 },
            ],
          },
        ]),
      }),
      null,
    );
    expect(cues).toHaveLength(1);
    expect(cues[0].words.map((w) => w.text)).toEqual(["Salut", "toi"]);
  });

  it("retourne [] sans texte ni cues", () => {
    expect(resolveCallCues(baseCall(), null)).toEqual([]);
  });
});
