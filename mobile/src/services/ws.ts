/**
 * Client WebSocket evenements VocalGuard.
 */

export type WsEventHandler = (event: { type: string; payload: Record<string, unknown> }) => void;

/**
 * Construit l URL WSS /ws/events avec token.
 *
 * @param baseUrl URL API ou nginx.
 * @param token Bearer API.
 */
export function buildWsUrl(baseUrl: string, token: string): string {
  const root = baseUrl.replace(/\/api\/v1\/?$/, "").replace(/\/$/, "");
  const wsRoot = root.replace(/^http/, "ws");
  return `${wsRoot}/ws/events?token=${encodeURIComponent(token)}`;
}

/**
 * Gestionnaire WS avec reconnexion exponentielle (LAN).
 */
export class VocalGuardWsClient {
  private ws: WebSocket | null = null;
  private retries = 0;
  private closed = false;

  /**
   * @param url URL WSS complete.
   * @param onEvent Callback evenement metier.
   * @param onStatus Changement etat connexion.
   */
  constructor(
    private readonly url: string,
    private readonly onEvent: WsEventHandler,
    private readonly onStatus?: (connected: boolean) => void,
  ) {}

  /** Ouvre la connexion WebSocket. */
  connect(): void {
    this.closed = false;
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => {
      this.retries = 0;
      this.onStatus?.(true);
    };
    this.ws.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(String(msg.data)) as {
          type: string;
          data?: Record<string, unknown>;
          payload?: Record<string, unknown>;
        };
        const payload = parsed.data ?? parsed.payload ?? {};
        this.onEvent({ type: parsed.type, payload });
      } catch {
        /* ignore malformed */
      }
    };
    this.ws.onclose = () => {
      this.onStatus?.(false);
      if (!this.closed) this.scheduleReconnect();
    };
    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  /** Ferme proprement sans reconnexion. */
  disconnect(): void {
    this.closed = true;
    this.ws?.close();
    this.ws = null;
  }

  private scheduleReconnect(): void {
    this.retries += 1;
    const delay = Math.min(30000, 1000 * 2 ** Math.min(this.retries, 5));
    setTimeout(() => {
      if (!this.closed) this.connect();
    }, delay);
  }
}
