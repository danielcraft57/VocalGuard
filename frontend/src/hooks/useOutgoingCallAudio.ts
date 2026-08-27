import { useEffect, useRef } from "react";
import { getOutgoingAudioWsBaseUrl } from "../services/httpClient";

/** Tampon initial (s) pour absorber le jitter WebSocket. */
const PLAYOUT_INITIAL_LATENCY_SEC = 0.22;
/** Recalage si la file prend trop de retard. */
const PLAYOUT_MAX_LEAD_SEC = 0.55;
const PLAYOUT_UNDERRUN_SEC = 0.08;

const DIAL_COMFORT_FREQ_HZ = 425;
const DIAL_COMFORT_GAIN = 0.05;

export type OutgoingDialPhase = "idle" | "dialing" | "connected" | "ended" | "error";

/**
 * Debloque l'AudioContext apres un geste utilisateur (clic Composer / Appeler).
 * A appeler depuis le handler de demarrage d'appel.
 */
export function unlockOutgoingAudioContext(): void {
  try {
    const AC =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    void ctx.resume().finally(() => {
      void ctx.close().catch(() => undefined);
    });
  } catch {
    /* ignore */
  }
}

/**
 * WebSocket audio sortant : ligne -> HP, micro -> ligne.
 * Socket stable pendant la session (mute sans reconnect).
 */
export function useOutgoingCallAudio(
  callId: number | null,
  sessionActive: boolean,
  listenActive: boolean,
  micActive: boolean,
  dialPhase: OutgoingDialPhase = "idle",
  onRemoteAudioDetected?: () => void
): void {
  const ctxRef = useRef<AudioContext | null>(null);
  const playHeadRef = useRef<number>(0);
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const procRef = useRef<ScriptProcessorNode | null>(null);
  const micGraphRef = useRef<{ ctx: AudioContext; mute: GainNode } | null>(null);
  const dialComfortStopRef = useRef<(() => void) | null>(null);
  const dialPhaseRef = useRef(dialPhase);
  const listenRef = useRef(listenActive);
  const micRef = useRef(micActive);
  const onRemoteRef = useRef(onRemoteAudioDetected);
  const remoteAudioSeenRef = useRef(false);

  dialPhaseRef.current = dialPhase;
  listenRef.current = listenActive;
  micRef.current = micActive;
  onRemoteRef.current = onRemoteAudioDetected;

  useEffect(() => {
    if (dialPhase !== "dialing") {
      const fn = dialComfortStopRef.current;
      dialComfortStopRef.current = null;
      fn?.();
    }
  }, [dialPhase]);

  useEffect(() => {
    if (callId === null || !sessionActive) {
      return;
    }

    const base = getOutgoingAudioWsBaseUrl();
    const ws = new WebSocket(`${base}/ws/outgoing-call/${callId}/audio`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;
    remoteAudioSeenRef.current = false;
    playHeadRef.current = 0;

    const stopDialComfort = () => {
      const fn = dialComfortStopRef.current;
      dialComfortStopRef.current = null;
      fn?.();
    };

    const ensurePlaybackCtx = (): AudioContext => {
      if (!ctxRef.current || ctxRef.current.state === "closed") {
        const AC =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        ctxRef.current = new AC!();
        playHeadRef.current = 0;
      }
      return ctxRef.current;
    };

    const startDialComfortIfNeeded = () => {
      if (!listenRef.current || dialPhaseRef.current !== "dialing") return;
      if (dialComfortStopRef.current) return;
      const ctx = ensurePlaybackCtx();
      void ctx.resume().catch(() => undefined);
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      gain.gain.value = DIAL_COMFORT_GAIN;
      osc.type = "sine";
      osc.frequency.value = DIAL_COMFORT_FREQ_HZ;
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      dialComfortStopRef.current = () => {
        try {
          osc.stop();
        } catch {
          /* ignore */
        }
        try {
          osc.disconnect();
          gain.disconnect();
        } catch {
          /* ignore */
        }
      };
    };

    ws.onmessage = (ev: MessageEvent<ArrayBuffer | Blob | string>) => {
      if (!listenRef.current) return;
      if (typeof ev.data === "string") return;

      const playPcm = (buf: ArrayBuffer) => {
        // s16le : longueur paire obligatoire
        const usable = buf.byteLength - (buf.byteLength % 2);
        if (usable < 2) return;
        const arr = new Int16Array(buf, 0, usable / 2);
        if (arr.length === 0) return;

        stopDialComfort();
        if (!remoteAudioSeenRef.current) {
          remoteAudioSeenRef.current = true;
          onRemoteRef.current?.();
        }

        const ctx = ensurePlaybackCtx();
        void ctx.resume().catch(() => undefined);

        const audioBuf = ctx.createBuffer(1, arr.length, 16000);
        const ch = audioBuf.getChannelData(0);
        for (let i = 0; i < arr.length; i++) {
          ch[i] = arr[i] / 32768;
        }
        const src = ctx.createBufferSource();
        src.buffer = audioBuf;
        src.connect(ctx.destination);

        let startAt = playHeadRef.current;
        const now = ctx.currentTime;
        if (startAt === 0 || startAt < now - PLAYOUT_UNDERRUN_SEC) {
          startAt = now + PLAYOUT_INITIAL_LATENCY_SEC;
        } else if (startAt > now + PLAYOUT_MAX_LEAD_SEC) {
          startAt = now + PLAYOUT_INITIAL_LATENCY_SEC * 0.7;
        }
        try {
          src.start(startAt);
          playHeadRef.current = startAt + audioBuf.duration;
        } catch {
          /* ignore schedule errors */
        }
      };

      if (ev.data instanceof Blob) {
        void ev.data.arrayBuffer().then(playPcm).catch(() => undefined);
        return;
      }
      playPcm(ev.data as ArrayBuffer);
    };

    ws.onopen = () => {
      void ensurePlaybackCtx().resume().catch(() => undefined);
      startDialComfortIfNeeded();
    };

    return () => {
      stopDialComfort();
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
      if (ctxRef.current) {
        try {
          void ctxRef.current.close();
        } catch {
          /* ignore */
        }
        ctxRef.current = null;
      }
      playHeadRef.current = 0;
    };
  }, [callId, sessionActive]);

  useEffect(() => {
    if (callId === null || !sessionActive || !micActive) {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      if (procRef.current) {
        try {
          procRef.current.disconnect();
        } catch {
          /* ignore */
        }
        procRef.current = null;
      }
      if (micGraphRef.current) {
        try {
          void micGraphRef.current.ctx.close();
        } catch {
          /* ignore */
        }
        micGraphRef.current = null;
      }
      return;
    }

    let cancelled = false;

    const startMic = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
          video: false
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const ctx = new AudioContext();
        const src = ctx.createMediaStreamSource(stream);
        const proc = ctx.createScriptProcessor(4096, 1, 1);
        const mute = ctx.createGain();
        mute.gain.value = 0;
        proc.onaudioprocess = (e: AudioProcessingEvent) => {
          const ws = wsRef.current;
          if (!ws || ws.readyState !== WebSocket.OPEN) return;
          if (!micRef.current) return;
          const input = e.inputBuffer.getChannelData(0);
          let peak = 0;
          for (let i = 0; i < input.length; i++) {
            const a = Math.abs(input[i] ?? 0);
            if (a > peak) peak = a;
          }
          // Seuil bas : on envoie la parole, on filtre le vrai silence.
          if (peak < 0.012) return;
          const ratio = ctx.sampleRate / 16000;
          const outLen = Math.max(1, Math.floor(input.length / ratio));
          const int16 = new Int16Array(outLen);
          for (let i = 0; i < outLen; i++) {
            const s = input[Math.floor(i * ratio)] ?? 0;
            int16[i] = Math.max(-32768, Math.min(32767, Math.round(s * 32767)));
          }
          ws.send(int16.buffer);
        };
        src.connect(proc);
        proc.connect(mute);
        mute.connect(ctx.destination);
        procRef.current = proc;
        micGraphRef.current = { ctx, mute };
      } catch {
        /* micro refuse */
      }
    };

    void startMic();

    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      if (procRef.current) {
        try {
          procRef.current.disconnect();
        } catch {
          /* ignore */
        }
        procRef.current = null;
      }
      if (micGraphRef.current) {
        try {
          void micGraphRef.current.ctx.close();
        } catch {
          /* ignore */
        }
        micGraphRef.current = null;
      }
    };
  }, [callId, sessionActive, micActive]);
}
