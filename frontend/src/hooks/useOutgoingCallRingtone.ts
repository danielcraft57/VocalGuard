import { useEffect, useRef } from "react";

/** Sonnerie type ligne fixe (approx. 425 Hz, impulsions ~1 s / ~5 s) pendant la composition. */
export function useOutgoingCallRingtone(status: "idle" | "dialing" | "connected" | "ended" | "error"): void {
  const ctxRef = useRef<AudioContext | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (status !== "dialing") {
      if (intervalRef.current != null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (ctxRef.current) {
        void ctxRef.current.close().catch(() => undefined);
        ctxRef.current = null;
      }
      return;
    }

    const playPulse = () => {
      try {
        let ctx = ctxRef.current;
        if (!ctx) {
          ctx = new AudioContext();
          ctxRef.current = ctx;
        }
        void ctx.resume().catch(() => undefined);
        const t0 = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(425, t0);
        gain.gain.setValueAtTime(0, t0);
        gain.gain.linearRampToValueAtTime(0.22, t0 + 0.04);
        gain.gain.setValueAtTime(0.2, t0 + 0.9);
        gain.gain.exponentialRampToValueAtTime(0.001, t0 + 1.05);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(t0);
        osc.stop(t0 + 1.08);
      } catch {
        /* navigateur sans Web Audio ou contexte suspendu */
      }
    };

    playPulse();
    intervalRef.current = setInterval(playPulse, 5000);

    return () => {
      if (intervalRef.current != null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (ctxRef.current) {
        void ctxRef.current.close().catch(() => undefined);
        ctxRef.current = null;
      }
    };
  }, [status]);
}

/** Bref signal positif a la connexion (deux tons courts). */
export function useOutgoingCallConnectChime(status: "idle" | "dialing" | "connected" | "ended" | "error"): void {
  const prev = useRef(status);

  useEffect(() => {
    if (prev.current !== "connected" && status === "connected") {
      try {
        const ctx = new AudioContext();
        void ctx.resume().then(() => {
          const playTone = (freq: number, when: number, dur: number) => {
            const o = ctx.createOscillator();
            const g = ctx.createGain();
            o.type = "sine";
            o.frequency.setValueAtTime(freq, when);
            g.gain.setValueAtTime(0, when);
            g.gain.linearRampToValueAtTime(0.12, when + 0.02);
            g.gain.exponentialRampToValueAtTime(0.001, when + dur);
            o.connect(g);
            g.connect(ctx.destination);
            o.start(when);
            o.stop(when + dur + 0.02);
          };
          const t0 = ctx.currentTime + 0.05;
          playTone(523.25, t0, 0.1);
          playTone(659.25, t0 + 0.12, 0.12);
          window.setTimeout(() => {
            void ctx.close().catch(() => undefined);
          }, 450);
        });
      } catch {
        /* ignore */
      }
    }
    prev.current = status;
  }, [status]);
}
