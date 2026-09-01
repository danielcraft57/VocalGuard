/** Tests client WebSocket. */
import { buildWsUrl, VocalGuardWsClient } from "./ws";

describe("ws", () => {
  it("construit l URL WSS avec token", () => {
    const url = buildWsUrl("https://vocalguard.test", "abc");
    expect(url).toContain("wss://vocalguard.test/ws/events");
    expect(url).toContain("token=abc");
  });

  it("notifie les evenements parses", () => {
    const events: string[] = [];
    const client = new VocalGuardWsClient("ws://test/events", (e) => events.push(e.type));
    const mockWs = {
      onopen: null as (() => void) | null,
      onmessage: null as ((msg: { data: string }) => void) | null,
      onclose: null as (() => void) | null,
      onerror: null as (() => void) | null,
      close: jest.fn(),
    };
    global.WebSocket = jest.fn(() => mockWs) as unknown as typeof WebSocket;
    client.connect();
    mockWs.onmessage?.({ data: JSON.stringify({ type: "call.incoming", data: { phone_number: "06" } }) });
    expect(events).toContain("call.incoming");
    client.disconnect();
  });

  it("accepte aussi le champ legacy payload", () => {
    const events: string[] = [];
    const client = new VocalGuardWsClient("ws://test/events", (e) => events.push(e.type));
    const mockWs = {
      onopen: null as (() => void) | null,
      onmessage: null as ((msg: { data: string }) => void) | null,
      onclose: null as (() => void) | null,
      onerror: null as (() => void) | null,
      close: jest.fn(),
    };
    global.WebSocket = jest.fn(() => mockWs) as unknown as typeof WebSocket;
    client.connect();
    mockWs.onmessage?.({ data: JSON.stringify({ type: "call.incoming", payload: { phone_number: "07" } }) });
    expect(events).toContain("call.incoming");
    client.disconnect();
  });
});
