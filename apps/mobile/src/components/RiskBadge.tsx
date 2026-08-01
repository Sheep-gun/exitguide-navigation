import { StyleSheet, Text } from "react-native";

import { colors, radii } from "../styles/theme";
import type { RiskLevel } from "../types";
import { riskLabel } from "../utils/labels";

type RiskBadgeProps = {
  risk: RiskLevel;
};

export function RiskBadge({ risk }: RiskBadgeProps) {
  return <Text style={[styles.badge, riskBadgeStyle(risk)]}>{riskLabel(risk)}</Text>;
}

function riskBadgeStyle(risk: RiskLevel) {
  if (risk === "high") {
    return styles.riskHigh;
  }
  if (risk === "medium") {
    return styles.riskMedium;
  }
  return styles.riskLow;
}

const styles = StyleSheet.create({
  badge: {
    borderRadius: radii.pill,
    color: colors.surface,
    fontSize: 12,
    fontWeight: "800",
    minWidth: 68,
    overflow: "hidden",
    paddingHorizontal: 10,
    paddingVertical: 5,
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
});
