import { StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { AnalysisHistoryItem, RiskLevel } from "../types";
import { riskLabel } from "../utils/labels";

type AnalysisHistoryProps = {
  items: AnalysisHistoryItem[];
  onClear: () => void;
  onOpen: (item: AnalysisHistoryItem) => void;
};

export function AnalysisHistory({ items, onClear, onOpen }: AnalysisHistoryProps) {
  if (!items.length) {
    return null;
  }

  return (
    <View style={styles.wrap}>
      <View style={styles.headerRow}>
        <Text style={styles.helper}>이 기기에 저장된 최근 단일 사진 분석 {items.length}개입니다.</Text>
        <TouchableOpacity accessibilityRole="button" onPress={onClear}>
          <Text style={styles.clear}>전체 지우기</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.list}>
        {items.map((item) => (
          <TouchableOpacity
            accessibilityRole="button"
            key={item.id}
            onPress={() => onOpen(item)}
            style={styles.card}
          >
            <View style={styles.cardHeader}>
              <Text style={styles.cardTitle}>{item.analysis.goal_label}</Text>
              <Text style={[styles.riskPill, riskPillStyle(item.analysis.overall_risk)]}>
                {riskLabel(item.analysis.overall_risk)}
              </Text>
            </View>
            <Text style={styles.meta}>
              {[item.createdAt, item.sourceLabel, item.analysis.screen_title, item.analysis.analysis_id].filter(Boolean).join(" | ")}
            </Text>
            <Text numberOfLines={2} style={styles.summary}>
              {item.analysis.summary}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

function riskPillStyle(risk: RiskLevel) {
  if (risk === "high") {
    return styles.riskHigh;
  }
  if (risk === "medium") {
    return styles.riskMedium;
  }
  return styles.riskLow;
}

const styles = StyleSheet.create({
  wrap: {
    gap: 10,
  },
  headerRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
  },
  helper: {
    color: colors.muted,
    flex: 1,
    fontSize: 13,
    lineHeight: 18,
  },
  clear: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "800",
  },
  list: {
    gap: 10,
  },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.card,
    borderWidth: 1,
    gap: 7,
    padding: 14,
  },
  cardHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  cardTitle: {
    color: colors.ink,
    flex: 1,
    fontSize: 15,
    fontWeight: "800",
  },
  riskPill: {
    borderRadius: radii.pill,
    color: colors.surface,
    fontSize: 11,
    fontWeight: "800",
    minWidth: 60,
    overflow: "hidden",
    paddingHorizontal: 9,
    paddingVertical: 4,
    textAlign: "center",
    textTransform: "uppercase",
  },
  riskHigh: {
    backgroundColor: colors.danger,
  },
  riskMedium: {
    backgroundColor: colors.warning,
  },
  riskLow: {
    backgroundColor: colors.primary,
  },
  meta: {
    color: colors.muted,
    fontSize: 12,
  },
  summary: {
    color: "#3F4650",
    fontSize: 13,
    lineHeight: 19,
  },
});
