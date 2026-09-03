/**
 * Decoupe une transcription en cues type SRT (4 a 5 mots) avec timestamps.
 */

export const TRANSCRIPT_WORDS_PER_CUE = 5;

export interface TranscriptWordCue {
  /** Mot affiche. */
  text: string;
  /** Debut relatif a l'audio (secondes). */
  start: number;
  /** Fin relative a l'audio (secondes). */
  end: number;
}

export interface TranscriptCue {
  /** Index 0-based. */
  index: number;
  /** Debut du groupe (secondes). */
  start: number;
  /** Fin du groupe (secondes). */
  end: number;
  /** Mots du groupe. */
  words: TranscriptWordCue[];
}

const WORD_RE = /\S+/g;

/**
 * Tokenise un texte en mots (ponctuation conservee sur le token).
 *
 * @param text Transcription brute.
 * @returns Liste de mots non vides.
 */
export function splitTranscriptWords(text: string): string[] {
  const trimmed = (text || "").trim();
  if (!trimmed) return [];
  return trimmed.match(WORD_RE) ?? [];
}

/**
 * Groupe les mots par paquets de 4-5 (dernier paquet fusionne s'il n'a qu'un mot).
 *
 * @param words Liste de mots.
 * @param wordsPerCue Taille cible (defaut 5).
 * @returns Groupes de mots.
 */
export function chunkWords(words: string[], wordsPerCue: number = TRANSCRIPT_WORDS_PER_CUE): string[][] {
  const size = Math.max(4, Math.min(5, Math.floor(wordsPerCue) || 5));
  if (words.length === 0) return [];
  const groups: string[][] = [];
  for (let i = 0; i < words.length; i += size) {
    groups.push(words.slice(i, i + size));
  }
  if (groups.length >= 2 && groups[groups.length - 1].length === 1) {
    const last = groups.pop();
    if (last) {
      groups[groups.length - 1].push(...last);
    }
  }
  return groups;
}

/**
 * Lit des cues deja stockes dans extra_data si le format est valide.
 *
 * @param extra Donnees extra de l'appel.
 * @returns Cues ou null.
 */
export function cuesFromExtraData(extra: Record<string, unknown> | null | undefined): TranscriptCue[] | null {
  if (!extra || typeof extra !== "object") return null;
  const raw = extra.transcription_cues;
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const cues: TranscriptCue[] = [];
  for (let i = 0; i < raw.length; i += 1) {
    const item = raw[i];
    if (!item || typeof item !== "object") return null;
    const rec = item as Record<string, unknown>;
    const start = Number(rec.start);
    const end = Number(rec.end);
    const wordsRaw = rec.words;
    if (!Number.isFinite(start) || !Number.isFinite(end) || !Array.isArray(wordsRaw)) {
      return null;
    }
    const words: TranscriptWordCue[] = [];
    for (const w of wordsRaw) {
      if (!w || typeof w !== "object") return null;
      const wr = w as Record<string, unknown>;
      const text = String(wr.text || "").trim();
      const ws = Number(wr.start);
      const we = Number(wr.end);
      if (!text || !Number.isFinite(ws) || !Number.isFinite(we)) return null;
      words.push({ text, start: ws, end: we });
    }
    if (words.length === 0) return null;
    cues.push({ index: i, start, end, words });
  }
  return cues;
}

/**
 * Construit des cues a partir de segments Whisper (start/end en secondes).
 *
 * @param segments Segments {start, end, text}.
 * @param wordsPerCue Taille des groupes.
 * @returns Cues SRT-like.
 */
export function buildCuesFromSegments(
  segments: Array<{ start: number; end: number; text: string }>,
  wordsPerCue: number = TRANSCRIPT_WORDS_PER_CUE
): TranscriptCue[] {
  const cues: TranscriptCue[] = [];
  for (const seg of segments) {
    const start = Number(seg.start);
    const end = Number(seg.end);
    const slice = buildTranscriptCues(seg.text || "", end - start, wordsPerCue);
    const offset = start;
    for (const cue of slice) {
      cues.push({
        index: cues.length,
        start: cue.start + offset,
        end: cue.end + offset,
        words: cue.words.map((w) => ({
          text: w.text,
          start: w.start + offset,
          end: w.end + offset
        }))
      });
    }
  }
  return cues;
}

/**
 * Construit des cues a partir d'un texte (timestamps proportionnels a la duree).
 *
 * @param text Transcription.
 * @param durationSec Duree audio (secondes). Minimum 1 s si texte present.
 * @param wordsPerCue Taille des groupes.
 * @returns Cues SRT-like.
 */
export function buildTranscriptCues(
  text: string,
  durationSec: number,
  wordsPerCue: number = TRANSCRIPT_WORDS_PER_CUE
): TranscriptCue[] {
  const words = splitTranscriptWords(text);
  if (words.length === 0) return [];
  const groups = chunkWords(words, wordsPerCue);
  const weights = groups.map((g) => g.reduce((acc, w) => acc + Math.max(w.length, 1), 0));
  const totalWeight = weights.reduce((a, b) => a + b, 0) || 1;
  const duration = Number.isFinite(durationSec) && durationSec > 0.4 ? durationSec : Math.max(groups.length * 1.6, 1);
  let cursor = 0;
  return groups.map((group, index) => {
    const slice = duration * (weights[index] / totalWeight);
    const start = cursor;
    const end = index === groups.length - 1 ? duration : cursor + slice;
    cursor = end;
    const groupWeight = weights[index] || 1;
    let wCursor = start;
    const wordCues: TranscriptWordCue[] = group.map((word, wi) => {
      const wSlice = (end - start) * (Math.max(word.length, 1) / groupWeight);
      const wStart = wCursor;
      const wEnd = wi === group.length - 1 ? end : wCursor + wSlice;
      wCursor = wEnd;
      return { text: word, start: wStart, end: wEnd };
    });
    return { index, start, end, words: wordCues };
  });
}

/**
 * Trouve l'index de cue actif pour un instant audio.
 *
 * @param cues Liste de cues.
 * @param timeSec Temps lecture.
 * @returns Index ou -1.
 */
export function findCueIndexAt(cues: TranscriptCue[], timeSec: number): number {
  if (cues.length === 0) return -1;
  const t = Math.max(0, timeSec);
  for (let i = 0; i < cues.length; i += 1) {
    if (t >= cues[i].start && t < cues[i].end) return i;
  }
  if (t >= cues[cues.length - 1].end) return cues.length - 1;
  return 0;
}

/**
 * Trouve l'index du mot actif dans un cue.
 *
 * @param cue Cue courant.
 * @param timeSec Temps lecture.
 * @returns Index mot.
 */
export function findWordIndexAt(cue: TranscriptCue, timeSec: number): number {
  const words = cue.words;
  if (words.length === 0) return 0;
  const t = Math.max(0, timeSec);
  for (let i = 0; i < words.length; i += 1) {
    if (t >= words[i].start && t < words[i].end) return i;
  }
  if (t >= words[words.length - 1].end) return words.length - 1;
  return 0;
}
