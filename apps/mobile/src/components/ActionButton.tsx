import type { PropsWithChildren } from "react";
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity } from "react-native";

import { colors, radii } from "../styles/theme";

type ActionButtonProps = PropsWithChildren<{
  disabled?: boolean;
  loading?: boolean;
  onPress: () => void;
  tone?: "primary" | "secondary";
}>;

export function ActionButton({
  children,
  disabled = false,
  loading = false,
  onPress,
  tone = "primary",
}: ActionButtonProps) {
  const isPrimary = tone === "primary";
  return (
    <TouchableOpacity
      accessibilityRole="button"
      accessibilityState={{ busy: loading, disabled: disabled || loading }}
      disabled={disabled || loading}
      onPress={onPress}
      style={[
        styles.button,
        isPrimary ? styles.primary : styles.secondary,
        (disabled || loading) && styles.disabled,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={isPrimary ? colors.surface : colors.primary} />
      ) : (
        <Text style={[styles.label, isPrimary ? styles.primaryLabel : styles.secondaryLabel]}>{children}</Text>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  button: {
    alignItems: "center",
    borderRadius: radii.control,
    justifyContent: "center",
    minHeight: 48,
    paddingHorizontal: 16,
  },
  primary: {
    backgroundColor: colors.ink,
  },
  secondary: {
    backgroundColor: colors.surface,
    borderColor: colors.primary,
    borderWidth: 1,
  },
  disabled: {
    backgroundColor: colors.disabled,
    borderColor: colors.disabled,
  },
  label: {
    fontSize: 15,
    fontWeight: "800",
    textAlign: "center",
  },
  primaryLabel: {
    color: colors.surface,
  },
  secondaryLabel: {
    color: colors.primary,
  },
});
