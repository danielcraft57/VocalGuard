/**
 * Genere une forme d onde deterministe (pas de decode audio).
 * Aligne mobile/frontend pour le scrubber Material.
 */

/**
 * Produit des hauteurs normalisees [0.18, 1] pour N barres.
 *
 * @param seed Identifiant (call id, duree, ...) pour stabiliser le rendu.
 * @param barCount Nombre de barres (defaut 48).
 * @returns Hauteurs 0-1.
 * @example
 * buildWaveformBars(163, 32)
 */
export function buildWaveformBars(seed: number, barCount: number = 48): number[] {
  const n = Math.max(8, Math.min(96, Math.floor(barCount) || 48));
  const s = Number.isFinite(seed) ? Math.abs(Math.floor(seed)) : 1;
  const bars: number[] = [];
  for (let i = 0; i < n; i += 1) {
    const x = Math.sin((i + 1) * 12.9898 + s * 78.233) * 43758.5453;
    const frac = x - Math.floor(x);
    const envelope = 0.35 + 0.65 * Math.sin((Math.PI * i) / Math.max(n - 1, 1));
    const h = 0.18 + frac * 0.82 * envelope;
    bars.push(Math.min(1, Math.max(0.18, h)));
  }
  return bars;
}

/**
 * Index de barre correspondant a un ratio de progression [0, 1].
 *
 * @param progress Ratio lecture.
 * @param barCount Nombre de barres.
 * @returns Index 0-based inclus.
 */
export function waveformIndexAt(progress: number, barCount: number): number {
  if (barCount <= 0) return 0;
  const p = Math.min(1, Math.max(0, Number.isFinite(progress) ? progress : 0));
  return Math.min(barCount - 1, Math.floor(p * barCount));
}
