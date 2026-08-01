import { StyleSheet, Text, View } from "react-native";

import { colors, radii } from "../styles/theme";

type EmptyStateProps = {
  message: string;
  title: string;
};

export function EmptyState({ message, title }: EmptyStateProps) {
  return (
    <View style={styles.panel}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.card,
    borderStyle: "dashed",
    borderWidth: 1,
    gap: 5,
    padding: 14,
  },
  title: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "800",
  },
  message: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 19,
  },
});
