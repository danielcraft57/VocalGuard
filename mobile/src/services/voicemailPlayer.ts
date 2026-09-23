/**
 * Lecteur audio messages vocaux (expo-audio, singleton).
 * Une seule piste a la fois ; seek borne (web HTMLMediaElement).
 */
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";
import { clampSeekSeconds } from "../utils/seekClamp";

export type VoicemailPlayerState = {
  activeId: number | null;
  loadingId: number | null;
  playing: boolean;
  currentTime: number;
  duration: number;
};

type Listener = (state: VoicemailPlayerState) => void;

let player: AudioPlayer | null = null;
let activeId: number | null = null;
let loadingId: number | null = null;
let listener: Listener | null = null;
let statusSub: { remove: () => void } | null = null;

const state: VoicemailPlayerState = {
  activeId: null,
  loadingId: null,
  playing: false,
  currentTime: 0,
  duration: 0,
};

/**
 * Abonne l UI aux changements du lecteur.
 *
 * @param fn Callback etat courant.
 * @returns Desabonnement.
 */
export function subscribeVoicemailPlayer(fn: Listener): () => void {
  listener = fn;
  fn({ ...state });
  return () => {
    if (listener === fn) listener = null;
  };
}

function emit(patch: Partial<VoicemailPlayerState>): void {
  Object.assign(state, patch);
  listener?.({ ...state });
}

function detachStatus(): void {
  statusSub?.remove();
  statusSub = null;
}

function releasePlayer(): void {
  detachStatus();
  if (player) {
    try {
      player.remove();
    } catch {
      /* ignore */
    }
    player = null;
  }
  activeId = null;
  emit({ activeId: null, playing: false, currentTime: 0, duration: 0 });
}

/**
 * Arrete la lecture en cours.
 */
export function stopVoicemailPlayback(): void {
  loadingId = null;
  emit({ loadingId: null });
  releasePlayer();
}

/**
 * Met en pause sans perdre la position.
 */
export function pauseVoicemailPlayback(): void {
  if (!player?.playing) return;
  player.pause();
  emit({ playing: false });
}

/**
 * Seek absolu (secondes).
 *
 * @param seconds Position cible.
 */
export function seekVoicemailPlayback(seconds: number): void {
  if (!player) return;
  const t = clampSeekSeconds(
    seconds,
    Number.isFinite(state.duration) && state.duration > 0 ? state.duration : undefined,
  );
  if (t == null) return;
  try {
    player.seekTo(t);
    emit({ currentTime: t });
  } catch {
    /* ignore */
  }
}

/**
 * Avance ou recule de N secondes.
 *
 * @param delta Secondes relatives.
 */
export function skipVoicemailPlayback(delta: number): void {
  if (!player) return;
  if (!Number.isFinite(delta)) return;
  const cur = Number.isFinite(state.currentTime) ? state.currentTime : 0;
  const dur = Number.isFinite(state.duration) && state.duration > 0 ? state.duration : undefined;
  const next = clampSeekSeconds(cur + delta, dur);
  if (next == null) return;
  seekVoicemailPlayback(next);
}

/**
 * Assure la lecture (sans pause si deja en play).
 *
 * @param id Identifiant.
 * @param uri URI audio.
 */
export async function ensureVoicemailPlaying(id: number, uri: string): Promise<void> {
  if (activeId === id && player) {
    if (!player.playing) {
      player.play();
      emit({ playing: true });
    }
    return;
  }
  await playVoicemailUri(id, uri);
}

/**
 * Lance ou reprend la lecture d un message (arrete l autre piste).
 *
 * @param id Identifiant message.
 * @param uri Fichier local / blob.
 */
export async function playVoicemailUri(id: number, uri: string): Promise<void> {
  await setAudioModeAsync({
    playsInSilentMode: true,
    interruptionMode: "mixWithOthers",
    allowsRecording: false,
    shouldPlayInBackground: false,
    shouldRouteThroughEarpiece: false,
  });

  if (activeId === id && player) {
    if (player.playing) {
      player.pause();
      emit({ playing: false });
      return;
    }
    player.play();
    emit({ playing: true });
    return;
  }

  // Nouvelle piste : coupe la precedente.
  releasePlayer();
  loadingId = id;
  emit({ loadingId: id, activeId: id });

  const next = createAudioPlayer({ uri }, { updateInterval: 200 });
  player = next;
  activeId = id;

  statusSub = next.addListener("playbackStatusUpdate", (status) => {
    if (!status.isLoaded) return;
    const currentTime = Number.isFinite(status.currentTime) ? status.currentTime : state.currentTime;
    const duration =
      Number.isFinite(status.duration) && status.duration > 0 ? status.duration : state.duration;
    emit({
      loadingId: null,
      playing: status.playing,
      currentTime,
      duration,
    });
    if (status.didJustFinish) {
      stopVoicemailPlayback();
    }
  });

  next.play();
  emit({ loadingId: null, playing: true });
}

/**
 * Bascule lecture / pause pour un message.
 *
 * @param id Identifiant message.
 * @param uri Fichier local.
 */
export async function toggleVoicemailPlayback(id: number, uri: string): Promise<void> {
  await playVoicemailUri(id, uri);
}
