import { StyleSheet, Text, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { AnalysisResponse } from "../types";

type RecommendedActionCardProps = {
  action: AnalysisResponse["recommended_action"];
};

export function RecommendedActionCard({ action }: RecommendedActionCardProps) {
  return (
    <View style={styles.card}>
      <Text style={styles.label}>추천 행동</Text>
      <Text style={styles.title}>{action.title}</Text>
      <Text style={styles.text}>{action.description}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primaryBorder,
    borderRadius: radii.card,
    borderWidth: 1,
    gap: 6,
    padding: 15,
  },
  label: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  title: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  text: {
    color: "#3F4650",
    fontSize: 14,
    lineHeight: 21,
  },
});
