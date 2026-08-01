import { StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { DemoScenario } from "../types";

type DemoScenarioListProps = {
  busy: boolean;
  scenarios: DemoScenario[];
  onRun: (scenario: DemoScenario) => void;
};

export function DemoScenarioList({ busy, onRun, scenarios }: DemoScenarioListProps) {
  return (
    <View style={styles.list}>
      {scenarios.map((scenario) => (
        <TouchableOpacity
          accessibilityRole="button"
          disabled={busy}
          key={scenario.id}
          onPress={() => onRun(scenario)}
          style={[styles.card, busy && styles.cardDisabled]}
        >
          <Text style={styles.title}>{scenario.title}</Text>
          <Text style={styles.description}>{scenario.description}</Text>
          <Text style={styles.cta}>데모 분석</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
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
  cardDisabled: {
    opacity: 0.65,
  },
  title: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
  },
  description: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
  },
  cta: {
    color: colors.primary,
    fontSize: 14,
    fontWeight: "800",
    marginTop: 2,
  },
});
