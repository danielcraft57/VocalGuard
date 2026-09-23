/** Tests decoupe transcription en cues karaoke. */
import {
  buildTranscriptCues,
  chunkWords,
  cuesFromExtraData,
  findCueIndexAt,
  findWordIndexAt,
  splitTranscriptWords,
} from "./transcriptCues";

describe("transcriptCues", () => {
  it("splitTranscriptWords conserve la ponctuation sur le token", () => {
    expect(splitTranscriptWords("Voila, voila, c est Louis.")).toEqual([
      "Voila,",
      "voila,",
      "c",
      "est",
      "Louis.",
    ]);
  });

  it("chunkWords groupe par 5 et fusionne un dernier mot seul", () => {
    const words = ["a", "b", "c", "d", "e", "f"];
    const groups = chunkWords(words, 5);
    expect(groups).toEqual([["a", "b", "c", "d", "e", "f"]]);
  });

  it("buildTranscriptCues produit des timestamps croissants", () => {
    const cues = buildTranscriptCues("Voila voila c est Louis", 10);
    expect(cues.length).toBeGreaterThan(0);
    expect(cues[0].start).toBe(0);
    expect(cues[cues.length - 1].end).toBeCloseTo(10, 1);
    for (let i = 1; i < cues.length; i += 1) {
      expect(cues[i].start).toBeGreaterThanOrEqual(cues[i - 1].start);
    }
  });

  it("cuesFromExtraData lit le format words", () => {
    const cues = cuesFromExtraData({
      transcription_cues: [
        {
          start: 0,
          end: 1.5,
          words: [
            { text: "Bonjour", start: 0, end: 0.7 },
            { text: "Alice", start: 0.7, end: 1.5 },
          ],
        },
      ],
    });
    expect(cues).not.toBeNull();
    expect(cues![0].words).toHaveLength(2);
  });

  it("findCueIndexAt et findWordIndexAt suivent le temps", () => {
    const cues = buildTranscriptCues("un deux trois quatre cinq", 5);
    expect(findCueIndexAt(cues, 0)).toBe(0);
    const cue = cues[0];
    expect(findWordIndexAt(cue, cue.words[0].start)).toBe(0);
  });
});
