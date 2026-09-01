/**
 * Audio appel sortant (WebSocket PCM via nginx).
 */

export type OutgoingState = "idle" | "dialing" | "connected" | "offline" | "error";

/**
 * Construit l URL WSS audio sortant.
 *
 * @param telephonyBase Base daemon (ex. wss://node12.lan/ws/outgoing-call).
 * @param callId Identifiant appel.
 */
export function buildOutgoingAudioWsUrl(telephonyBase: string, callId: number): string {
  const base = telephonyBase.replace(/\/$/, "");
  return `${base}/${callId}/audio`;
}

/**
 * Etat dialer selon connectivite LAN.
 *
 * @param online Serveur joignable.
 */
export function resolveOutgoingState(online: boolean): OutgoingState {
  return online ? "idle" : "offline";
}

/**
 * Envoie un buffer PCM sur le WebSocket ouvert.
 *
 * @param ws WebSocket actif.
 * @param pcm Chunk PCM 16-bit mono.
 */
export function sendPcmChunk(ws: WebSocket | null, pcm: ArrayBuffer): boolean {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  ws.send(pcm);
  return true;
}

/**
 * Demande raccrochage cote REST.
 *
 * @param fetchFn Fetch injectable (tests).
 * @param apiUrl Base API avec Bearer.
 * @param token Token API.
 * @param callId ID appel.
 */
export async function hangupOutgoingCall(
  apiUrl: string,
  token: string,
  callId: number,
  fetchFn: typeof fetch = fetch,
): Promise<boolean> {
  const root = apiUrl.replace(/\/$/, "");
  const url = root.endsWith("/api/v1")
    ? `${root}/public/calls/outgoing/${callId}/hangup`
    : `${root}/api/v1/public/calls/outgoing/${callId}/hangup`;
  const res = await fetchFn(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.ok;
}
