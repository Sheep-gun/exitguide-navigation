import { StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { DemoFlow } from "../types";

type DemoFlowListProps = {
  busy: boolean;
  flows: DemoFlow[];
  onRun: (flow: DemoFlow) => void;
};

export function DemoFlowList({ busy, flows, onRun }: DemoFlowListProps) {
  return (
    <View style={styles.list}>
      {flows.map((flow) => (
        <TouchableOpacity
          accessibilityRole="button"
          disabled={busy}
          key={flow.id}
          onPress={() => onRun(flow)}
          style={[styles.card, busy && styles.cardDisabled]}
        >
          <Text style={styles.title}>{flow.title}</Text>
          <Text style={styles.description}>{flow.description}</Text>
          <Text style={styles.meta}>{flow.scenarioIds.length}개 화면 | 흐름 분석</Text>
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
    padding: 15,
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
  meta: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "800",
  },
});
