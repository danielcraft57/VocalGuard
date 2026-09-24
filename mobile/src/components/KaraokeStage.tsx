import React, { useMemo } from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import type { TranscriptCue } from "../utils/transcriptCues";
import { findCueIndexAt, findWordIndexAt } from "../utils/transcriptCues";
import { colors } from "../theme/colors";

const WORD_COLORS = ["#4ade80", "#38bdf8", "#fbbf24", "#c084fc", "#fb7185"];

type Props = {
  cues: TranscriptCue[];
  currentTime: number;
  onSeekWord: (startSec: number) => void;
  onSeekCue?: (startSec: number) => void;
};

/**
 * Scene karaoke alignee web : bulles colorees, barre cue, dots, compteur.
 */
export function KaraokeStage({ cues, currentTime, onSeekWord, onSeekCue }: Props) {
  const cueIndex = useMemo(() => findCueIndexAt(cues, currentTime), [cues, currentTime]);
  const cue = cueIndex >= 0 ? cues[cueIndex] : undefined;
  const wordIndex = cue ? findWordIndexAt(cue, currentTime) : 0;

  const cueProgress = useMemo(() => {
    if (!cue || cue.words.length === 0) return 0;
    return Math.min(1, Math.max(0, (wordIndex + 0.5) / cue.words.length));
  }, [cue, wordIndex]);

  if (!cues.length) {
    return (
      <View style={styles.emptyWrap}>
        <Text style={styles.empty}>Pas encore de transcription.</Text>
      </View>
    );
  }

  if (!cue) {
    return (
      <View style={styles.emptyWrap}>
        <Text style={styles.empty}>Transcription en attente...</Text>
      </View>
    );
  }

  const seekCue = onSeekCue ?? onSeekWord;

  return (
    <View style={styles.stage}>
      <View style={styles.wordsRow}>
        {cue.words.map((word, i) => {
          const active = i === wordIndex;
          const color = WORD_COLORS[i % WORD_COLORS.length];
          return (
            <Pressable
              key={`${cue.index}-${i}-${word.text}`}
              onPress={() => onSeekWord(word.start)}
              style={[
                styles.wordBtn,
                {
                  backgroundColor: active ? `${color}26` : "rgba(255,255,255,0.04)",
                  transform: [{ translateY: active ? -8 : 0 }, { scale: active ? 1.08 : 1 }],
                  shadowColor: active ? color : "transparent",
                  shadowOpacity: active ? 0.35 : 0,
                  shadowRadius: active ? 14 : 0,
                  elevation: active ? 4 : 0,
                },
              ]}
              accessibilityLabel={`Aller a ${word.text}`}
              accessibilityState={{ selected: active }}
            >
              <Text
                style={[
                  styles.wordText,
                  {
                    color,
                    fontWeight: active ? "800" : "600",
                    fontSize: active ? 28 : 18,
                    opacity: active ? 1 : 0.62,
                  },
                ]}
              >
                {word.text}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.progressTrack}>
        <View
          style={[
            styles.progressFill,
            {
              width: `${cueProgress * 100}%`,
              backgroundColor: WORD_COLORS[wordIndex % WORD_COLORS.length],
            },
          ]}
        />
      </View>

      {cues.length > 1 ? (
        <View style={styles.dots}>
          {cues.map((item, i) => (
            <Pressable
              key={`dot-${item.index}`}
              onPress={() => seekCue(item.start)}
              accessibilityLabel={`Groupe ${i + 1}`}
              style={[styles.dot, i === cueIndex && styles.dotActive]}
            />
          ))}
        </View>
      ) : null}

      <Text style={styles.hint}>
        {cueIndex + 1} / {cues.length}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  stage: {
    minHeight: 188,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 16,
    gap: 12,
  },
  progressTrack: {
    width: "70%",
    maxWidth: 280,
    height: 4,
    borderRadius: 99,
    backgroundColor: "rgba(255,255,255,0.08)",
    overflow: "hidden",
    marginTop: 6,
  },
  progressFill: {
    height: 4,
    borderRadius: 99,
  },
  wordsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "center",
    alignItems: "flex-end",
    gap: 10,
    maxWidth: 520,
    minHeight: 92,
  },
  wordBtn: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 999,
  },
  wordText: {
    lineHeight: 32,
  },
  dots: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "center",
    alignItems: "center",
    gap: 6,
    marginTop: 4,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 99,
    backgroundColor: "rgba(148,163,184,0.45)",
  },
  dotActive: {
    width: 18,
    backgroundColor: colors.primary,
  },
  hint: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: "600",
    letterSpacing: 1.2,
  },
  emptyWrap: {
    minHeight: 120,
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
  },
  empty: {
    color: colors.textMuted,
    textAlign: "center",
    fontSize: 14,
  },
});
