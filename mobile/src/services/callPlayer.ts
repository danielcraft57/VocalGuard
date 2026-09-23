/**
 * Lecteur audio appels (expo-audio, singleton) avec seek pour karaoke.
 */
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";

export type CallPlayerState = {
  activeId: number | null;
  loadingId: number | null;
  playing: boolean;
  currentTime: number;
  duration: number;
};

type Listener = (state: CallPlayerState) => void;

let player: AudioPlayer | null = null;
let activeId: number | null = null;
let loadingId: number | null = null;
let listener: Listener | null = null;
let statusSub: { remove: () => void } | null = null;

const state: CallPlayerState = {
  activeId: null,
  loadingId: null,
  playing: false,
  currentTime: 0,
  duration: 0,
};

/**
 * Abonne l UI aux changements du lecteur appel.
 *
 * @param fn Callback etat courant.
 * @returns Desabonnement.
 */
export function subscribeCallPlayer(fn: Listener): () => void {
  listener = fn;
  fn({ ...state });
  return () => {
    if (listener === fn) listener = null;
  };
}

function emit(patch: Partial<CallPlayerState>): void {
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
export function stopCallPlayback(): void {
  loadingId = null;
  emit({ loadingId: null });
  releasePlayer();
}

/**
 * Met en pause sans perdre la position.
 */
export function pauseCallPlayback(): void {
  if (!player?.playing) return;
  player.pause();
  emit({ playing: false });
}

/**
 * Seek absolu (secondes) pour karaoke / barre.
 *
 * @param seconds Position cible.
 */
export function seekCallPlayback(seconds: number): void {
  if (!player) return;
  const t = Math.max(0, seconds);
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
 * @param delta Secundes relatives (ex. -5 ou +5).
 */
export function skipCallPlayback(delta: number): void {
  if (!player) return;
  const dur = state.duration > 0 ? state.duration : Number.POSITIVE_INFINITY;
  const next = Math.min(dur, Math.max(0, state.currentTime + delta));
  seekCallPlayback(next);
}

/**
 * Assure que la lecture tourne (sans basculer en pause si deja en lecture).
 *
 * @param id Identifiant appel.
 * @param uri Fichier local.
 */
export async function ensureCallPlaying(id: number, uri: string): Promise<void> {
  if (activeId === id && player) {
    if (!player.playing) {
      player.play();
      emit({ playing: true });
    }
    return;
  }
  await playCallUri(id, uri);
}

/**
 * Lance ou reprend la lecture d un enregistrement d appel.
 *
 * @param id Identifiant appel.
 * @param uri Fichier local file://
 */
export async function playCallUri(id: number, uri: string): Promise<void> {
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

  releasePlayer();
  loadingId = id;
  emit({ loadingId: id, activeId: id });

  const next = createAudioPlayer({ uri }, { updateInterval: 200 });
  player = next;
  activeId = id;

  statusSub = next.addListener("playbackStatusUpdate", (status) => {
    if (!status.isLoaded) return;
    emit({
      loadingId: null,
      playing: status.playing,
      currentTime: status.currentTime,
      duration: status.duration > 0 ? status.duration : state.duration,
    });
    if (status.didJustFinish) {
      stopCallPlayback();
    }
  });

  next.play();
  emit({ loadingId: null, playing: true });
}

/**
 * Bascule lecture / pause pour un appel.
 *
 * @param id Identifiant appel.
 * @param uri Fichier local.
 */
export async function toggleCallPlayback(id: number, uri: string): Promise<void> {
  await playCallUri(id, uri);
}
