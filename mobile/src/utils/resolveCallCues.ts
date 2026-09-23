/**
 * Resolution des cues karaoke a partir du detail API et/ou du cache local.
 */
import type { CallRow } from "../db/schema";
import { parseCallCuesJson } from "../db/schema";
import {
  buildTranscriptCues,
  compactOverlongCues,
  cuesFromExtraData,
  type TranscriptCue,
} from "./transcriptCues";

/** Detail minimal utile pour le karaoke (API ou partiel). */
export type CallCuesSource = {
  no_message?: boolean | null;
  transcription?: string | null;
  duration?: number | null;
  extra_data?: Record<string, unknown> | null;
};

/**
 * Construit les cues karaoke pour un appel.
 * Priorite : cues detail API > cues cache local > texte (proportionnel a la duree).
 *
 * @param call Ligne SQLite locale (peut etre null).
 * @param detail Detail API (peut etre null si 404).
 * @returns Cues pret pour KaraokeStage.
 * @example
 * resolveCallCues({ transcription: "Bonjour", duration: 2 }, null)
 */
export function resolveCallCues(
  call: CallRow | null | undefined,
  detail: CallCuesSource | null | undefined,
): TranscriptCue[] {
  if (detail?.no_message || call?.no_message) return [];

  const fromDetail = cuesFromExtraData(detail?.extra_data ?? null);
  if (fromDetail?.length) return compactOverlongCues(fromDetail);

  const localCues = parseCallCuesJson(call?.transcription_cues_json);
  if (localCues) {
    const fromLocal = cuesFromExtraData({ transcription_cues: localCues });
    if (fromLocal?.length) return compactOverlongCues(fromLocal);
  }

  const text = (detail?.transcription ?? call?.transcription ?? "").trim();
  if (!text) return [];
  const dur =
    Number(detail?.duration ?? call?.duration ?? 0) || Math.max(text.split(/\s+/).length * 0.4, 2);
  return buildTranscriptCues(text, dur);
}
