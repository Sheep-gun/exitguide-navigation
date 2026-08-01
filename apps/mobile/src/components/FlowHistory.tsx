import { StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { FlowHistoryItem } from "../types";
import { RiskBadge } from "./RiskBadge";

type FlowHistoryProps = {
  items: FlowHistoryItem[];
  onClear: () => void;
  onOpen: (item: FlowHistoryItem) => void;
};

export function FlowHistory({ items, onClear, onOpen }: FlowHistoryProps) {
  if (!items.length) {
    return null;
  }

  return (
    <View style={styles.wrap}>
      <View style={styles.headerRow}>
        <Text style={styles.helper}>이 기기에 저장된 최근 흐름 분석 {items.length}개입니다.</Text>
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
              <Text style={styles.cardTitle}>{item.flow.goal_label}</Text>
              <RiskBadge risk={item.flow.overall_risk} />
            </View>
            <Text style={styles.meta}>
              {[item.createdAt, item.sourceLabel, `${item.flow.screens.length}개 화면`, item.flow.flow_id].filter(Boolean).join(" | ")}
            </Text>
            <Text numberOfLines={2} style={styles.summary}>
              {item.flow.summary}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
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
