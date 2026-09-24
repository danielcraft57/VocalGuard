/** Tests client appel sortant (API + WS). */
import {
  buildOutgoingAudioWsUrl,
  deriveTelephonyWsBaseFromApi,
} from "./outgoingCall";

describe("outgoingCall", () => {
  it("derive WS 8090 depuis API 8000", () => {
    expect(deriveTelephonyWsBaseFromApi("http://node14.lan:8000")).toBe(
      "ws://node14.lan:8090/ws/outgoing-call",
    );
    expect(deriveTelephonyWsBaseFromApi("http://node14.lan:8000/api/v1")).toBe(
      "ws://node14.lan:8090/ws/outgoing-call",
    );
  });

  it("construit URL audio complete", () => {
    expect(buildOutgoingAudioWsUrl("ws://h:8090", 3)).toBe(
      "ws://h:8090/ws/outgoing-call/3/audio",
    );
    expect(buildOutgoingAudioWsUrl("ws://h:8090/ws/outgoing-call", 3)).toBe(
      "ws://h:8090/ws/outgoing-call/3/audio",
    );
  });
});
