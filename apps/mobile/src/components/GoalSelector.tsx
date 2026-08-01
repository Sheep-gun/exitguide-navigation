import { StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { Goal } from "../types";

type GoalSelectorProps = {
  goals: Goal[];
  selectedGoalId: string;
  onSelect: (goalId: string) => void;
};

export function GoalSelector({ goals, onSelect, selectedGoalId }: GoalSelectorProps) {
  const selectedGoal = goals.find((goal) => goal.id === selectedGoalId) ?? goals[0];
  const supportingGoals = goals.filter((goal) => goal.id !== selectedGoal?.id);

  return (
    <View style={styles.wrap}>
      {selectedGoal ? (
        <View style={styles.currentCard}>
          <Text style={styles.currentLabel}>통합 분석 기준</Text>
          <Text style={styles.currentTitle}>{selectedGoal.title}</Text>
          <Text style={styles.currentDescription}>{selectedGoal.description}</Text>
        </View>
      ) : null}
      <View style={styles.chipRow}>
        {supportingGoals.map((goal) => {
        const active = selectedGoalId === goal.id;
        return (
          <TouchableOpacity
            accessibilityRole="button"
            key={goal.id}
            onPress={() => onSelect(goal.id)}
            style={[styles.goalButton, active && styles.goalButtonActive]}
          >
            <Text style={[styles.goalTitle, active && styles.goalTitleActive]}>{goal.title}</Text>
          </TouchableOpacity>
        );
      })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 10,
  },
  currentCard: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primaryBorder,
    borderRadius: radii.card,
    borderWidth: 1,
    gap: 5,
    padding: 14,
  },
  currentLabel: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "900",
  },
  currentTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
  },
  currentDescription: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 19,
  },
  chipRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  goalButton: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.pill,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  goalButtonActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  goalTitle: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "800",
  },
  goalTitleActive: {
    color: colors.surface,
  },
});
