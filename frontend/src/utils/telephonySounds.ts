/**
 * Sons type téléphone (Web Audio API) — touches DTMF, composition, raccrochage.
 * Le premier geste utilisateur débloque souvent l’audio (policy navigateur).
 */

let sharedCtx: AudioContext | null = null;

function getCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  try {
    if (!sharedCtx || sharedCtx.state === "closed") {
      sharedCtx = new AudioContext();
    }
    void sharedCtx.resume().catch(() => undefined);
    return sharedCtx;
  } catch {
    return null;
  }
}

/** Paires basses/hautes fréquences DTMF (ITU-T Q.23). */
const DTMF_PAIR: Record<string, [number, number]> = {
  "1": [697, 1209],
  "2": [697, 1336],
  "3": [697, 1477],
  "4": [770, 1209],
  "5": [770, 1336],
  "6": [770, 1477],
  "7": [852, 1209],
  "8": [852, 1336],
  "9": [852, 1477],
  "*": [941, 1209],
  "0": [941, 1336],
  "#": [941, 1477]
};

function beepDual(freq1: number, freq2: number, durationMs: number, gainPeak: number): void {
  const ctx = getCtx();
  if (!ctx) return;
  const t0 = ctx.currentTime;
  const dur = durationMs / 1000;
  const o1 = ctx.createOscillator();
  const o2 = ctx.createOscillator();
  const g = ctx.createGain();
  o1.type = "sine";
  o2.type = "sine";
  o1.frequency.setValueAtTime(freq1, t0);
  o2.frequency.setValueAtTime(freq2, t0);
  g.gain.setValueAtTime(0, t0);
  g.gain.linearRampToValueAtTime(gainPeak, t0 + 0.015);
  g.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
  o1.connect(g);
  o2.connect(g);
  g.connect(ctx.destination);
  o1.start(t0);
  o2.start(t0);
  o1.stop(t0 + dur + 0.02);
  o2.stop(t0 + dur + 0.02);
}

/** Touche clavier (composition ou DTMF en ligne). */
export function playDialerKeySound(digit: string): void {
  const pair = DTMF_PAIR[digit];
  if (!pair) return;
  beepDual(pair[0], pair[1], 110, 0.14);
}

/** Début d’appel (double bip court). */
export function playOutgoingDialSound(): void {
  const ctx = getCtx();
  if (!ctx) return;
  const t0 = ctx.currentTime;
  const pulse = (start: number, f: number) => {
    const o = ctx!.createOscillator();
    const g = ctx!.createGain();
    o.type = "sine";
    o.frequency.setValueAtTime(f, start);
    g.gain.setValueAtTime(0, start);
    g.gain.linearRampToValueAtTime(0.16, start + 0.02);
    g.gain.exponentialRampToValueAtTime(0.001, start + 0.14);
    o.connect(g);
    g.connect(ctx!.destination);
    o.start(start);
    o.stop(start + 0.16);
  };
  pulse(t0 + 0.02, 480);
  pulse(t0 + 0.22, 620);
}

/** Raccrochage : glissement descendant bref. */
export function playHangupSound(): void {
  const ctx = getCtx();
  if (!ctx) return;
  const t0 = ctx.currentTime;
  const o = ctx.createOscillator();
  const g = ctx.createGain();
  o.type = "sine";
  o.frequency.setValueAtTime(520, t0);
  o.frequency.exponentialRampToValueAtTime(220, t0 + 0.18);
  g.gain.setValueAtTime(0, t0);
  g.gain.linearRampToValueAtTime(0.12, t0 + 0.02);
  g.gain.exponentialRampToValueAtTime(0.001, t0 + 0.22);
  o.connect(g);
  g.connect(ctx.destination);
  o.start(t0);
  o.stop(t0 + 0.25);
}
