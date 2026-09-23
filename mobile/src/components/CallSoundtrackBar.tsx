import React, { useMemo, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { buildWaveformBars, waveformIndexAt } from "../utils/waveformBars";
import { colors } from "../theme/colors";
import { icons } from "../theme/icons";

const SKIP_SEC = 2;

type Props = {
  callId: number;
  currentTime: number;
  duration: number;
  playing: boolean;
  loading?: boolean;
  disabled?: boolean;
  cueMarks?: number[];
  onTogglePlay: () => void;
  onSeekRatio: (ratio: number) => void;
  onSkip: (delta: number) => void;
  error?: string | null;
};

/**
 * Horloge mm:ss.
 *
 * @param sec Secondes.
 */
function formatClock(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0:00";
  const s = Math.floor(sec);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

/**
 * Bande sonore : cadre haut, waveform, controles en calque semi-transparent (±2 s).
 */
export function CallSoundtrackBar({
  callId,
  currentTime,
  duration,
  playing,
  loading = false,
  disabled = false,
  cueMarks = [],
  onTogglePlay,
  onSeekRatio,
  onSkip,
  error,
}: Props) {
  const [scrubbing, setScrubbing] = useState(false);
  const widthRef = useRef(0);
  const bars = useMemo(
    () => buildWaveformBars(callId * 17 + Math.round(duration), 56),
    [callId, duration],
  );
  const progress = duration > 0 ? Math.min(1, currentTime / duration) : 0;
  const filledUntil = waveformIndexAt(progress, bars.length);

  if (error) {
    return (
      <View style={styles.wrap}>
        <View style={styles.labelRow}>
          <MaterialCommunityIcons name="equalizer" size={16} color={colors.textMuted} />
          <Text style={styles.label}>Bande sonore</Text>
        </View>
        <View style={[styles.frame, styles.frameError]}>
          <Text style={styles.error}>{error}</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.wrap}>
      <View style={styles.labelRow}>
        <MaterialCommunityIcons name="equalizer" size={16} color={colors.textMuted} />
        <Text style={styles.label}>Bande sonore</Text>
      </View>

      <View style={[styles.frame, scrubbing && styles.frameScrubbing]}>
        <Pressable
          style={styles.waveHit}
          disabled={disabled || loading}
          onLayout={(e) => {
            widthRef.current = e.nativeEvent.layout.width;
          }}
          onPressIn={() => setScrubbing(true)}
          onPressOut={() => setScrubbing(false)}
          onPress={(e) => {
            if (widthRef.current <= 0 || disabled || loading) return;
            onSeekRatio(e.nativeEvent.locationX / widthRef.current);
          }}
          accessibilityRole="adjustable"
          accessibilityLabel="Position lecture"
        >
          <View style={styles.waveRow}>
            {bars.map((h, i) => {
              const played = i <= filledUntil;
              return (
                <View
                  key={`bar-${i}`}
                  style={[
                    styles.bar,
                    {
                      height: `${Math.max(12, h * 100)}%`,
                      backgroundColor: played ? colors.primary : "rgba(148,163,184,0.38)",
                      opacity: played ? 1 : 0.75,
                    },
                  ]}
                />
              );
            })}
          </View>
          {cueMarks.map((mark, i) => {
            if (duration <= 0) return null;
            const pct = Math.min(100, Math.max(0, (mark / duration) * 100));
            return (
              <View
                key={`mark-${i}`}
                style={[styles.mark, { left: `${pct}%` as `${number}%` }]}
                pointerEvents="none"
              />
            );
          })}
        </Pressable>

        {/* Calque controles semi-transparent au-dessus de la waveform. */}
        <View style={styles.overlay} pointerEvents="box-none">
          <View style={styles.overlayGlass}>
            <Pressable
              onPress={() => onSkip(-SKIP_SEC)}
              disabled={disabled || loading}
              hitSlop={10}
              accessibilityLabel={`Reculer ${SKIP_SEC} secondes`}
              style={[styles.skipPill, (disabled || loading) && styles.ctrlDisabled]}
            >
              <MaterialCommunityIcons name="rewind" size={18} color={colors.text} />
              <Text style={styles.skipLabel}>2</Text>
            </Pressable>

            <Pressable
              onPress={onTogglePlay}
              disabled={disabled || loading}
              style={[styles.playFab, (disabled || loading) && styles.playDisabled]}
              accessibilityLabel={playing ? "Pause" : "Lecture"}
            >
              {loading ? (
                <ActivityIndicator color={colors.slate} />
              ) : (
                <MaterialCommunityIcons
                  name={playing ? icons.pause : icons.play}
                  size={30}
                  color={colors.slate}
                />
              )}
            </Pressable>

            <Pressable
              onPress={() => onSkip(SKIP_SEC)}
              disabled={disabled || loading}
              hitSlop={10}
              accessibilityLabel={`Avancer ${SKIP_SEC} secondes`}
              style={[styles.skipPill, (disabled || loading) && styles.ctrlDisabled]}
            >
              <Text style={styles.skipLabel}>2</Text>
              <MaterialCommunityIcons name="fast-forward" size={18} color={colors.text} />
            </Pressable>
          </View>
        </View>

        {loading ? (
          <View style={styles.loaderMask} pointerEvents="none">
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={styles.loaderText}>Chargement audio...</Text>
          </View>
        ) : null}
      </View>

      <View style={styles.times}>
        <Text style={styles.clock}>{formatClock(currentTime)}</Text>
        <Text style={styles.clock}>{formatClock(duration)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingHorizontal: 14, paddingBottom: 12, gap: 10 },
  labelRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  label: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 1.2,
  },
  frame: {
    position: "relative",
    height: 132,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(148,163,184,0.22)",
    backgroundColor: "rgba(15,20,28,0.55)",
    overflow: "hidden",
  },
  frameScrubbing: {
    borderColor: "rgba(34,197,94,0.45)",
  },
  frameError: {
    height: 96,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  waveHit: {
    ...StyleSheet.absoluteFillObject,
    paddingHorizontal: 10,
    paddingVertical: 16,
    justifyContent: "flex-end",
  },
  waveRow: {
    flex: 1,
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 2,
  },
  bar: {
    flex: 1,
    minHeight: 6,
    borderRadius: 99,
  },
  mark: {
    position: "absolute",
    top: 12,
    bottom: 12,
    width: 2,
    marginLeft: -1,
    borderRadius: 99,
    backgroundColor: "#fbbf24",
    opacity: 0.55,
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
  },
  overlayGlass: {
    flexDirection: "row",
    alignItems: "center",
    gap: 18,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 999,
    backgroundColor: "rgba(15, 23, 42, 0.42)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
  },
  skipPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.08)",
  },
  skipLabel: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
  },
  playFab: {
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    opacity: 0.95,
  },
  playDisabled: { opacity: 0.4 },
  ctrlDisabled: { opacity: 0.4 },
  loaderMask: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(15, 23, 42, 0.55)",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },
  loaderText: {
    color: colors.textMuted,
    fontSize: 13,
    fontWeight: "600",
  },
  times: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  clock: {
    color: colors.textMuted,
    fontSize: 12,
    fontVariant: ["tabular-nums"],
  },
  error: {
    color: colors.textMuted,
    textAlign: "center",
    fontSize: 13,
  },
});
