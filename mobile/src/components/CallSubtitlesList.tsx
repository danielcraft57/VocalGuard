/**
 * Liste sous-titres : conserve pour reutilisation, mais le detail
 * aligne web utilise KaraokeStage dans le cadre Sous-titres unique.
 */
import React, { useEffect, useRef } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import type { TranscriptCue } from "../utils/transcriptCues";
import { findCueIndexAt } from "../utils/transcriptCues";
import { colors } from "../theme/colors";

type Props = {
  cues: TranscriptCue[];
  fullText: string | null;
  currentTime: number;
  onSeekCue: (startSec: number) => void;
};

/**
 * Liste chronologique des cues (optionnelle hors cadre Sous-titres).
 */
export function CallSubtitlesList({ cues, fullText, currentTime, onSeekCue }: Props) {
  const activeIndex = findCueIndexAt(cues, currentTime);
  const scrollRef = useRef<ScrollView>(null);
  const rowYs = useRef<Map<number, number>>(new Map());

  useEffect(() => {
    if (activeIndex < 0) return;
    const y = rowYs.current.get(activeIndex);
    if (y != null) {
      scrollRef.current?.scrollTo({ y: Math.max(0, y - 40), animated: true });
    }
  }, [activeIndex]);

  if (!cues.length && !fullText?.trim()) {
    return (
      <View style={styles.wrap}>
        <Text style={styles.empty}>Pas de transcription pour cet appel.</Text>
      </View>
    );
  }

  if (!cues.length && fullText?.trim()) {
    return (
      <View style={styles.wrap}>
        <Text style={styles.fullText}>{fullText.trim()}</Text>
      </View>
    );
  }

  return (
    <View style={styles.wrap}>
      <ScrollView
        ref={scrollRef}
        style={styles.list}
        nestedScrollEnabled
        showsVerticalScrollIndicator={false}
      >
        {cues.map((cue, i) => {
          const active = i === activeIndex;
          const line = cue.words.map((w) => w.text).join(" ");
          return (
            <Pressable
              key={`sub-${cue.index}-${i}`}
              onLayout={(e) => {
                rowYs.current.set(i, e.nativeEvent.layout.y);
              }}
              onPress={() => onSeekCue(cue.start)}
              style={[styles.row, active && styles.rowActive]}
            >
              <Text style={[styles.time, active && styles.timeActive]}>
                {formatClock(cue.start)}
              </Text>
              <Text style={[styles.line, active && styles.lineActive]}>{line}</Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

/**
 * Horloge mm:ss courte.
 *
 * @param sec Secondes.
 */
function formatClock(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0:00";
  const s = Math.floor(sec);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

const styles = StyleSheet.create({
  wrap: { gap: 10, maxHeight: 280 },
  empty: { color: colors.textMuted, fontSize: 13 },
  fullText: { color: colors.neutral200, fontSize: 14, lineHeight: 22 },
  list: { maxHeight: 220 },
  row: {
    flexDirection: "row",
    gap: 10,
    paddingVertical: 8,
    paddingHorizontal: 8,
    borderRadius: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "rgba(148,163,184,0.15)",
  },
  rowActive: {
    backgroundColor: "rgba(34, 197, 94, 0.12)",
  },
  time: {
    color: colors.textMuted,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    width: 40,
    paddingTop: 2,
  },
  timeActive: { color: colors.primary, fontWeight: "700" },
  line: { color: colors.neutral200, fontSize: 14, lineHeight: 20, flex: 1 },
  lineActive: { color: colors.text, fontWeight: "600" },
});
