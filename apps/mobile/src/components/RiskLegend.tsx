import { StyleSheet, Text, View } from "react-native";

import { colors, radii } from "../styles/theme";

export function RiskLegend() {
  return (
    <View style={styles.card}>
      <LegendItem color={colors.danger} label="높음" text="목표와 충돌하거나 비용/선택 동의에 영향을 줄 수 있습니다." />
      <LegendItem color={colors.warning} label="주의" text="계속하기 전에 사용자가 직접 확인해야 합니다." />
      <LegendItem color={colors.primary} label="낮음" text="목표와 대체로 맞거나 정보성 요소로 보입니다." />
    </View>
  );
}

type LegendItemProps = {
  color: string;
  label: string;
  text: string;
};

function LegendItem({ color, label, text }: LegendItemProps) {
  return (
    <View style={styles.item}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.text}>{text}</Text>
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
  item: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  dot: {
    borderRadius: radii.pill,
    height: 10,
    width: 10,
  },
  label: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "800",
    width: 54,
  },
  text: {
    color: colors.muted,
    flex: 1,
    fontSize: 12,
    lineHeight: 17,
  },
});
