/**
 * Helpers seek audio (sans dependance expo-audio, testables en Jest).
 */

/**
 * Normalise une position seek (rejette NaN/Infinity, borne a la duree).
 *
 * @param seconds Position demandee.
 * @param duration Duree connue (optionnelle).
 * @returns Secondes valides ou null si invalide.
 */
export function clampSeekSeconds(seconds: number, duration?: number): number | null {
  if (!Number.isFinite(seconds)) return null;
  let t = Math.max(0, seconds);
  if (duration != null && Number.isFinite(duration) && duration > 0) {
    t = Math.min(t, duration);
  }
  return t;
}
