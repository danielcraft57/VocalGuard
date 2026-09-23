/** Tests detection direction appels. */
import { getCallDirection } from "./callDirection";

describe("getCallDirection", () => {
  it("detecte sortant via caller_name", () => {
    expect(getCallDirection({ caller_name: "Sortant" })).toBe("out");
  });

  it("detecte sortant via audio_file", () => {
    expect(getCallDirection({ audio_file: "recordings/call_out_12.wav" })).toBe("out");
  });

  it("defaut entrant", () => {
    expect(getCallDirection({ caller_name: "Alice", audio_file: "recordings/call_in_1.wav" })).toBe("in");
  });
});
