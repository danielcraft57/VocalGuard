import React from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import type { CallRow } from "../db/schema";
import { parseCallOsint } from "../db/schema";
import { CallStatusBadge } from "./CallStatusBadge";
import { getCallDirection } from "../utils/callDirection";
import { formatCallTime, formatDuration, formatPhone } from "../utils/format";
import {
  formatOsintMeta,
  getReputationCategory,
  getReputationColor,
  getReputationLabel,
} from "../utils/osintLabels";
import { colors } from "../theme/colors";
import { icons } from "../theme/icons";

type Props = {
  item: CallRow;
  onPress: (item: CallRow) => void;
};

/**
 * Ligne de la liste appels : direction, numero FR, OSINT, badge statut.
 */
export function CallListItem({ item, onPress }: Props) {
  const osint = parseCallOsint(item.osint_json);
  const direction = getCallDirection({
    caller_name: item.caller_name,
    audio_file: item.audio_file,
  });
  const phoneFmt = item.phone_number ? formatPhone(item.phone_number) : "";
  const name = (item.caller_name ?? "").trim();
  const isOutgoingLabel = name.toLowerCase() === "sortant";
  const title = !isOutgoingLabel && name ? name : phoneFmt || "Inconnu";
  const subtitle = !isOutgoingLabel && name && phoneFmt ? phoneFmt : null;
  const osintMeta = formatOsintMeta(osint);
  const company = (osint?.company_name || osint?.name || "").trim();
  const duration = formatDuration(item.duration);
  const repCat = getReputationCategory(osint);
  const repColors = getReputationColor(repCat);
  const directionIcon = direction === "out" ? icons.outgoing : icons.incoming;
  const directionColor = direction === "out" ? "#38bdf8" : colors.primary;

  return (
    <Pressable
      style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
      onPress={() => onPress(item)}
      accessibilityRole="button"
      accessibilityLabel={`Appel ${direction === "out" ? "sortant" : "entrant"} ${title}`}
    >
      <View style={[styles.iconWrap, { backgroundColor: `${directionColor}22` }]}>
        <MaterialCommunityIcons name={directionIcon} size={22} color={directionColor} />
      </View>
      <View style={styles.body}>
        <View style={styles.titleRow}>
          <Text style={styles.title} numberOfLines={1}>
            {title}
          </Text>
          <Text style={styles.time}>{formatCallTime(item.call_time)}</Text>
        </View>
        {subtitle ? (
          <Text style={styles.subtitle} numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
        {company && company !== name ? (
          <Text style={styles.company} numberOfLines={1}>
            {company}
          </Text>
        ) : null}
        {osintMeta && !company ? (
          <Text style={styles.osintMeta} numberOfLines={1}>
            {osintMeta}
          </Text>
        ) : osint && (osint.operator || osint.city) ? (
          <Text style={styles.osintMeta} numberOfLines={1}>
            {[osint.operator, osint.city].filter(Boolean).join(" · ")}
          </Text>
        ) : null}
        <View style={styles.metaRow}>
          <CallStatusBadge status={item.status} />
          {osint ? (
            <View style={[styles.repChip, { backgroundColor: repColors.bg }]}>
              <Text style={[styles.repText, { color: repColors.fg }]}>
                {getReputationLabel(osint)}
              </Text>
            </View>
          ) : null}
          {duration ? <Text style={styles.duration}>{duration}</Text> : null}
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.slateLight,
    gap: 12,
  },
  rowPressed: { backgroundColor: colors.slateLight },
  iconWrap: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  body: { flex: 1, minWidth: 0 },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  title: { color: colors.text, fontSize: 16, fontWeight: "600", flex: 1 },
  time: { color: colors.textMuted, fontSize: 12 },
  subtitle: { color: colors.textMuted, fontSize: 13, marginTop: 2 },
  company: { color: colors.neutral200, fontSize: 13, marginTop: 2, fontWeight: "500" },
  osintMeta: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 6, flexWrap: "wrap" },
  repChip: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 999,
  },
  repText: { fontSize: 11, fontWeight: "600" },
  duration: { color: colors.textMuted, fontSize: 12 },
});
