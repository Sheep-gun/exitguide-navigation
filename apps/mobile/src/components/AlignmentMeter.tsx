import { StyleSheet, Text, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { AnalysisResponse } from "../types";

type AlignmentMeterProps = {
  analysis: AnalysisResponse;
};

export function AlignmentMeter({ analysis }: AlignmentMeterProps) {
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.label}>목표 일치도</Text>
        <Text style={styles.score}>{analysis.alignment_score}/100</Text>
      </View>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${analysis.alignment_score}%` }]} />
      </View>
      <Text style={styles.counts}>
        높음 {analysis.risk_counts.high} | 주의 {analysis.risk_counts.medium} | 낮음 {analysis.risk_counts.low}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.card,
    borderWidth: 1,
    gap: 8,
    padding: 12,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  label: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "800",
  },
  score: {
    color: colors.primary,
    fontSize: 14,
    fontWeight: "800",
  },
  track: {
    backgroundColor: "#E8ECF2",
    borderRadius: radii.pill,
    height: 9,
    overflow: "hidden",
  },
  fill: {
    backgroundColor: colors.primary,
    borderRadius: radii.pill,
    height: 9,
  },
  counts: {
    color: colors.muted,
    fontSize: 12,
  },
});
