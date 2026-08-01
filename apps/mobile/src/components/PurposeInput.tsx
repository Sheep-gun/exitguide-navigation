import { ActivityIndicator, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";

import { colors, radii } from "../styles/theme";

type PurposeInputProps = {
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
  onStart: () => void;
  startDisabled?: boolean;
  startLoading?: boolean;
};

export function PurposeInput({
  value,
  onChange,
  onClear,
  onStart,
  startDisabled = false,
  startLoading = false,
}: PurposeInputProps) {
  const hasValue = Boolean(value.trim());

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <View style={styles.headerText}>
          <Text style={styles.eyebrow}>통합 목적</Text>
          <Text style={styles.title}>무엇을 지키고 싶나요?</Text>
        </View>
        <View style={styles.headerActions}>
          {hasValue ? (
            <TouchableOpacity
              accessibilityRole="button"
              onPress={() => {
                onChange("");
                onClear();
              }}
              style={styles.clearButton}
            >
              <Text style={styles.clearText}>비우기</Text>
            </TouchableOpacity>
          ) : null}
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityState={{ busy: startLoading, disabled: startDisabled || startLoading }}
            disabled={startDisabled || startLoading}
            onPress={onStart}
            style={[styles.startButton, (startDisabled || startLoading) && styles.startButtonDisabled]}
          >
            {startLoading ? (
              <ActivityIndicator color={colors.surface} size="small" />
            ) : (
              <Text style={styles.startText}>탐색 시작</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
      <TextInput
        multiline
        onChangeText={onChange}
        placeholder="예: 추가 결제 없이 가입하고 싶어요"
        placeholderTextColor="#8A929D"
        style={styles.input}
        textAlignVertical="top"
        value={value}
      />
      <Text style={styles.helper}>
        입력하면 모든 분석이 이 문장을 기준으로 움직입니다. 비워두면 AI가 화면 문맥에서 목적을 추론합니다.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.card,
    borderWidth: 1,
    gap: 12,
    padding: 15,
  },
  headerRow: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
  },
  headerText: {
    flex: 1,
    gap: 4,
  },
  headerActions: {
    alignItems: "center",
    flexDirection: "row",
    gap: 7,
  },
  eyebrow: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "900",
  },
  title: {
    color: colors.ink,
    fontSize: 19,
    fontWeight: "900",
  },
  clearButton: {
    borderColor: colors.border,
    borderRadius: radii.pill,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  clearText: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "800",
  },
  startButton: {
    alignItems: "center",
    backgroundColor: colors.ink,
    borderRadius: radii.control,
    justifyContent: "center",
    minHeight: 38,
    minWidth: 88,
    paddingHorizontal: 12,
  },
  startButtonDisabled: {
    backgroundColor: colors.disabled,
  },
  startText: {
    color: colors.surface,
    fontSize: 13,
    fontWeight: "900",
  },
  input: {
    backgroundColor: "#F7F9FC",
    borderColor: colors.border,
    borderRadius: radii.control,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 16,
    lineHeight: 22,
    minHeight: 92,
    paddingHorizontal: 13,
    paddingVertical: 12,
  },
  helper: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 19,
  },
});
