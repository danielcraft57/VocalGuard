/**
 * Session audio live appel sortant (WebSocket PCM s16le 16 kHz).
 *
 * - Web (Expo web) : Web Audio API (micro + HP), comme le dialer Next.
 * - Natif : WS + playout downlink via petits WAV (expo-audio) ; micro full-duplex
 *   natif limite sans module PCM (l uplink reste vide, le stub VoIP envoie du silence).
 */

import { Platform } from "react-native";
import { File, Paths } from "expo-file-system";
import { createAudioPlayer, type AudioPlayer } from "expo-audio";
import { log } from "./log";
import { buildOutgoingAudioWsUrl } from "./outgoingCall";
import { sendPcmChunk } from "./outgoingAudio";

const TARGET_RATE = 16000;

export type LiveAudioStatus = "idle" | "connecting" | "open" | "closed" | "error";

export interface LiveOutgoingAudioHandlers {
  onStatus?: (status: LiveAudioStatus) => void;
  onRemoteAudio?: () => void;
}

/**
 * Encode PCM s16le mono en WAV (header RIFF).
 *
 * @param pcm Octets PCM.
 * @param sampleRate Hz.
 * @returns Buffer WAV.
 */
export function pcmS16leToWav(pcm: ArrayBuffer, sampleRate: number = TARGET_RATE): ArrayBuffer {
  const dataLen = pcm.byteLength;
  const buffer = new ArrayBuffer(44 + dataLen);
  const view = new DataView(buffer);
  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataLen, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, dataLen, true);
  new Uint8Array(buffer, 44).set(new Uint8Array(pcm));
  return buffer;
}

/**
 * Session audio bidirectionnelle (best-effort selon plateforme).
 */
export class LiveOutgoingAudioSession {
  private ws: WebSocket | null = null;
  private closed = false;
  private webCtx: AudioContext | null = null;
  private webProc: ScriptProcessorNode | null = null;
  private webStream: MediaStream | null = null;
  private playHead = 0;
  private nativePlayer: AudioPlayer | null = null;
  private nativeQueue: ArrayBuffer[] = [];
  private nativePlaying = false;
  private chunkIndex = 0;

  /**
   * @param telephonyBase Base WS (ws://host:8090/ws/outgoing-call).
   * @param callId Session.
   * @param handlers Callbacks.
   */
  constructor(
    private readonly telephonyBase: string,
    private readonly callId: number,
    private readonly handlers: LiveOutgoingAudioHandlers = {},
  ) {}

  /** Ouvre le WebSocket et demarre capture/playout. */
  start(): void {
    this.closed = false;
    const url = buildOutgoingAudioWsUrl(this.telephonyBase, this.callId);
    this.handlers.onStatus?.("connecting");
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    this.ws = ws;

    ws.onopen = () => {
      this.handlers.onStatus?.("open");
      if (Platform.OS === "web") {
        void this.startWebDuplex();
      }
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data === "string") return;
      const pcm = ev.data as ArrayBuffer;
      if (!pcm || pcm.byteLength < 4) return;
      this.handlers.onRemoteAudio?.();
      if (Platform.OS === "web") {
        this.playWebPcm(pcm);
      } else {
        this.enqueueNativePcm(pcm);
      }
    };
    ws.onerror = () => {
      this.handlers.onStatus?.("error");
    };
    ws.onclose = () => {
      this.handlers.onStatus?.("closed");
      void this.teardownMedia();
    };
  }

  /** Ferme WS + media. */
  stop(): void {
    this.closed = true;
    try {
      this.ws?.close();
    } catch {
      /* ignore */
    }
    this.ws = null;
    void this.teardownMedia();
    this.handlers.onStatus?.("closed");
  }

  /**
   * Envoie du PCM uplink.
   *
   * @param pcm Buffer.
   * @returns True si envoye.
   */
  sendPcm(pcm: ArrayBuffer): boolean {
    return sendPcmChunk(this.ws, pcm);
  }

  private async teardownMedia(): Promise<void> {
    try {
      this.webProc?.disconnect();
      this.webProc = null;
      this.webStream?.getTracks().forEach((t) => t.stop());
      this.webStream = null;
      await this.webCtx?.close();
    } catch {
      /* ignore */
    }
    this.webCtx = null;
    try {
      this.nativePlayer?.remove();
    } catch {
      /* ignore */
    }
    this.nativePlayer = null;
    this.nativeQueue = [];
    this.nativePlaying = false;
  }

  private async startWebDuplex(): Promise<void> {
    if (typeof window === "undefined") return;
    try {
      const AC =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AC) return;
      const ctx = new AC({ sampleRate: TARGET_RATE });
      this.webCtx = ctx;
      await ctx.resume();
      this.playHead = ctx.currentTime + 0.2;
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
        },
      });
      this.webStream = stream;
      const source = ctx.createMediaStreamSource(stream);
      const proc = ctx.createScriptProcessor(2048, 1, 1);
      this.webProc = proc;
      proc.onaudioprocess = (e) => {
        if (this.closed || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        const input = e.inputBuffer.getChannelData(0);
        const out = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
          const s = Math.max(-1, Math.min(1, input[i]));
          out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        this.ws.send(out.buffer);
      };
      source.connect(proc);
      proc.connect(ctx.destination);
    } catch (err) {
      log.warn("liveAudio", "web duplex failed", err);
    }
  }

  private playWebPcm(pcm: ArrayBuffer): void {
    const ctx = this.webCtx;
    if (!ctx || this.closed) return;
    const samples = new Int16Array(pcm);
    if (samples.length === 0) return;
    const buf = ctx.createBuffer(1, samples.length, TARGET_RATE);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < samples.length; i++) {
      ch[i] = samples[i] / 32768;
    }
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    const now = ctx.currentTime;
    if (this.playHead < now + 0.05) this.playHead = now + 0.08;
    src.start(this.playHead);
    this.playHead += buf.duration;
  }

  private enqueueNativePcm(pcm: ArrayBuffer): void {
    this.nativeQueue.push(pcm.slice(0));
    if (this.nativeQueue.length > 40) {
      this.nativeQueue.splice(0, this.nativeQueue.length - 40);
    }
    void this.drainNativeQueue();
  }

  private async drainNativeQueue(): Promise<void> {
    if (this.nativePlaying || this.closed) return;
    const chunk = this.nativeQueue.shift();
    if (!chunk) return;
    this.nativePlaying = true;
    try {
      const wav = pcmS16leToWav(chunk);
      const bytes = new Uint8Array(wav);
      const name = `vg_out_${this.callId}_${this.chunkIndex++}.wav`;
      const file = new File(Paths.cache, name);
      const writer = file.writableStream().getWriter();
      await writer.write(bytes);
      await writer.close();
      const raw = (file as unknown as { uri: string }).uri;
      if (!raw) throw new Error("uri audio manquante");
      const uri = raw.startsWith("file://") ? raw : `file://${raw}`;
      const player = createAudioPlayer(uri);
      this.nativePlayer = player;
      player.play();
      const durationMs = Math.max(200, (chunk.byteLength / 2 / TARGET_RATE) * 1000 + 80);
      await new Promise<void>((resolve) => {
        setTimeout(resolve, durationMs);
      });
      try {
        player.remove();
      } catch {
        /* ignore */
      }
      try {
        file.delete();
      } catch {
        /* ignore */
      }
    } catch (err) {
      log.warn("liveAudio", "native playout failed", err);
    } finally {
      this.nativePlaying = false;
      if (this.nativeQueue.length > 0) {
        void this.drainNativeQueue();
      }
    }
  }
}
