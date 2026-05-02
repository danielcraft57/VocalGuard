import { useEffect, useRef } from "react";
import { getOutgoingAudioWsBaseUrl } from "../services/httpClient";

/** Tampon de lecture (s) : retarde le premier sample pour absorber le jitter reseau / WebSocket. */
const PLAYOUT_INITIAL_LATENCY_SEC = 0.14;
/** Si la tete de lecture retarde trop sur l'horloge audio, on resynchronise. */
const PLAYOUT_RESYNC_LATE_SEC = 0.06;

/**
 * Branche WebSocket audio pour un appel sortant actif : ligne -> haut-parleurs, micro -> ligne.
 * Planification continue des BufferSource pour limiter les trous entre chunks PCM.
 */
export function useOutgoingCallAudio(
  callId: number | null,
  listenActive: boolean,
  micActive: boolean
): void {
  const ctxRef = useRef<AudioContext | null>(null);
  const playHeadRef = useRef<number>(0);
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const procRef = useRef<ScriptProcessorNode | null>(null);
  const micGraphRef = useRef<{ ctx: AudioContext; mute: GainNode } | null>(null);

  useEffect(() => {
    if (callId === null || (!listenActive && !micActive)) {
      return;
    }

    const base = getOutgoingAudioWsBaseUrl();
    const ws = new WebSocket(`${base}/ws/outgoing-call/${callId}/audio`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    const ensurePlaybackCtx = (): AudioContext => {
      if (!ctxRef.current) {
        ctxRef.current = new AudioContext();
        playHeadRef.current = 0;
      }
      return ctxRef.current;
    };

    ws.onmessage = (ev: MessageEvent<ArrayBuffer | string>) => {
      if (!listenActive) return;
      if (typeof ev.data === "string") return;
      const arr = new Int16Array(ev.data as ArrayBuffer);
      if (arr.length === 0) return;
      const ctx = ensurePlaybackCtx();
      void ctx.resume().catch(() => undefined);

      const buf = ctx.createBuffer(1, arr.length, 16000);
      const ch = buf.getChannelData(0);
      for (let i = 0; i < arr.length; i++) {
        ch[i] = arr[i] / 32768;
      }
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);

      let startAt = playHeadRef.current;
      if (startAt === 0) {
        startAt = ctx.currentTime + PLAYOUT_INITIAL_LATENCY_SEC;
      } else if (startAt < ctx.currentTime - PLAYOUT_RESYNC_LATE_SEC) {
        startAt = ctx.currentTime + PLAYOUT_INITIAL_LATENCY_SEC * 0.5;
      }
      src.start(startAt);
      playHeadRef.current = startAt + buf.duration;
    };

    let cancelled = false;

    const startMic = async () => {
      if (!micActive || cancelled) return;
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
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
          if (ws.readyState !== WebSocket.OPEN) return;
          const input = e.inputBuffer.getChannelData(0);
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
        /* micro refuse ou HTTPS requis */
      }
    };

    ws.onopen = () => {
      void ensurePlaybackCtx().resume().catch(() => undefined);
      void startMic();
    };

    return () => {
      cancelled = true;
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
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
  }, [callId, listenActive, micActive]);
}
