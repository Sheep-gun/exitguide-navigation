import type { PropsWithChildren } from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors } from "../styles/theme";

type SectionProps = PropsWithChildren<{
  title: string;
}>;

export function Section({ children, title }: SectionProps) {
  return (
    <View style={styles.section}>
      <Text style={styles.title}>{title}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    gap: 12,
  },
  title: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
  },
});
