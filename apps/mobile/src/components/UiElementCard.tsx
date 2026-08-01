import { StyleSheet, Text, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { UiElement } from "../types";
import { RiskBadge } from "./RiskBadge";

type UiElementCardProps = {
  element: UiElement;
  recommendedTargetId: string | null;
};

export function UiElementCard({ element, recommendedTargetId }: UiElementCardProps) {
  const isRecommendedTarget = recommendedTargetId === element.id;

  return (
    <View style={[styles.card, isRecommendedTarget && styles.recommendedCard]}>
      <View style={styles.header}>
        <Text style={styles.label}>{element.label}</Text>
        <RiskBadge risk={element.risk_level} />
      </View>
      {isRecommendedTarget ? <Text style={styles.recommended}>추천 대상</Text> : null}
      {element.signals?.length ? (
        <View style={styles.signalRow}>
          {element.signals.map((signal) => (
            <Text key={signal} style={styles.signal}>
              {signal}
            </Text>
          ))}
        </View>
      ) : null}
      <Text style={styles.direction}>{formatDirection(element.direction)}</Text>
      <Text style={styles.reason}>{element.reason}</Text>
    </View>
  );
}

function formatDirection(direction: UiElement["direction"]) {
  if (direction === "supports_goal") {
    return "목표에 맞는 선택지";
  }
  if (direction === "conflicts_with_goal") {
    return "목표와 충돌 가능";
  }
  return "사용자 확인 필요";
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.card,
    borderWidth: 1,
    gap: 8,
    padding: 14,
  },
  recommendedCard: {
    borderColor: colors.primary,
    borderWidth: 2,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  label: {
    color: colors.ink,
    flex: 1,
    fontSize: 16,
    fontWeight: "800",
  },
  recommended: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  signalRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
  signal: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primaryBorder,
    borderRadius: radii.pill,
    borderWidth: 1,
    color: colors.primary,
    fontSize: 11,
    fontWeight: "800",
    overflow: "hidden",
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  direction: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "800",
  },
  reason: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
  },
});
