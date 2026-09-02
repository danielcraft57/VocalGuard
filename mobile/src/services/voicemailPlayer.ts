/**
 * Lecteur audio messages vocaux (expo-audio, singleton).
 */
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";

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
 * Lance ou reprend la lecture d un message.
 *
 * @param id Identifiant message.
 * @param uri Fichier local file://
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

  releasePlayer();
  loadingId = id;
  emit({ loadingId: id, activeId: id });

  const next = createAudioPlayer({ uri }, { updateInterval: 250 });
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
