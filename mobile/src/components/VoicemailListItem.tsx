import React, { useMemo } from "react";
import { View, Text, StyleSheet } from "react-native";
import type { VoicemailRow } from "../db/schema";
import type { VoicemailPlayerState } from "../services/voicemailPlayer";
import { CallSoundtrackBar } from "./CallSoundtrackBar";
import { formatCallTime, voicemailCallerLabel } from "../utils/format";
import { colors } from "../theme/colors";

type Props = {
  item: VoicemailRow;
  player: VoicemailPlayerState;
  playError?: string | null;
  onTogglePlay: () => void;
  onSeekRatio: (ratio: number) => void;
  onSkip: (delta: number) => void;
};

/**
 * Ligne message vocal avec bande sonore interactive (waveform + seek).
 */
export function VoicemailListItem({
  item,
  player,
  playError,
  onTogglePlay,
  onSeekRatio,
  onSkip,
}: Props) {
  const caller = useMemo(
    () => voicemailCallerLabel(item.caller_name, item.caller_number),
    [item.caller_name, item.caller_number],
  );
  const isActive = player.activeId === item.id;
  const isLoading = player.loadingId === item.id;
  const isPlaying = isActive && player.playing;
  const callDur = Number.isFinite(item.duration) ? item.duration : 0;
  const playerDur = isActive && Number.isFinite(player.duration) ? player.duration : 0;
  const duration = Math.max(playerDur, callDur, 1);
  const currentTime =
    isActive && Number.isFinite(player.currentTime) ? player.currentTime : 0;
  const pendingStt =
    !item.transcription?.trim() &&
    !!item.recorded_at &&
    Date.now() - Date.parse(item.recorded_at) < 2 * 60 * 60 * 1000;

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.phone}>
          {caller.title}
          {!item.is_read ? " · nouveau" : ""}
        </Text>
        {caller.subtitle ? <Text style={styles.subPhone}>{caller.subtitle}</Text> : null}
        {item.transcription ? (
          <Text style={styles.transcription} numberOfLines={3}>
            {item.transcription}
          </Text>
        ) : pendingStt ? (
          <Text style={styles.transcriptionPending}>Transcription en cours...</Text>
        ) : null}
        <Text style={styles.meta}>
          {item.is_read ? "Lu" : "Non lu"}
          {item.recorded_at ? ` · ${formatCallTime(item.recorded_at)}` : ""}
        </Text>
      </View>

      <CallSoundtrackBar
        callId={item.id}
        currentTime={currentTime}
        duration={duration}
        playing={isPlaying}
        loading={isLoading}
        disabled={false}
        onTogglePlay={onTogglePlay}
        onSeekRatio={onSeekRatio}
        onSkip={onSkip}
        error={isActive ? playError : null}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderBottomWidth: 1,
    borderBottomColor: colors.slateLight,
    paddingTop: 14,
    paddingBottom: 6,
    backgroundColor: colors.slate,
  },
  header: { paddingHorizontal: 16, gap: 2 },
  phone: { color: colors.text, fontSize: 16, fontWeight: "600" },
  subPhone: { color: colors.textMuted, marginTop: 2, fontSize: 13 },
  transcription: { color: colors.text, marginTop: 6, fontSize: 14, lineHeight: 20 },
  transcriptionPending: {
    color: colors.textMuted,
    marginTop: 6,
    fontSize: 13,
    fontStyle: "italic",
  },
  meta: { color: colors.textMuted, marginTop: 4, marginBottom: 4, fontSize: 12 },
});
