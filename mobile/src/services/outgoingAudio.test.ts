/** Tests audio sortant / dialer. */
import {
  buildOutgoingAudioWsUrl,
  hangupOutgoingCall,
  resolveOutgoingState,
  sendPcmChunk,
} from "./outgoingAudio";

describe("outgoingAudio", () => {
  it("grise le dialer offline", () => {
    expect(resolveOutgoingState(false)).toBe("offline");
    expect(resolveOutgoingState(true)).toBe("idle");
  });

  it("construit URL WS PCM", () => {
    expect(buildOutgoingAudioWsUrl("wss://node12.lan/ws/outgoing-call", 42)).toContain("/42/audio");
  });

  it("envoie PCM si WS ouvert", () => {
    const ws = { readyState: 1, send: jest.fn() } as unknown as WebSocket;
    expect(sendPcmChunk(ws, new ArrayBuffer(8))).toBe(true);
    expect(ws.send).toHaveBeenCalled();
  });

  it("hangup REST", async () => {
    const fetchFn = jest.fn().mockResolvedValue({ ok: true });
    const ok = await hangupOutgoingCall("https://test", "tok", 7, fetchFn);
    expect(ok).toBe(true);
  });
});
