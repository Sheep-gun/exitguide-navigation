import { StyleSheet, Text, View } from "react-native";

import { colors, radii } from "../styles/theme";

type MessagePanelProps = {
  message: string;
  title: string;
};

export function MessagePanel({ message, title }: MessagePanelProps) {
  return (
    <View style={styles.panel}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    backgroundColor: colors.errorSurface,
    borderColor: colors.errorBorder,
    borderRadius: radii.card,
    borderWidth: 1,
    gap: 5,
    padding: 14,
  },
  title: {
    color: colors.errorInk,
    fontSize: 15,
    fontWeight: "800",
  },
  message: {
    color: "#68302A",
    fontSize: 14,
    lineHeight: 20,
  },
});
