import { StyleSheet, Text, View } from "react-native";

import { colors } from "../styles/theme";

export function AppHeader() {
  return (
    <View style={styles.header}>
      <Text style={styles.kicker}>ExitGuide AI</Text>
      <Text style={styles.title}>불필요한 유도를 한 번에 걸러냅니다.</Text>
      <Text style={styles.subtitle}>
        해지 방해, 추가 결제, 선택 동의, 탈퇴 방해를 하나의 분석 기준으로 확인하세요.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    gap: 10,
    paddingTop: 24,
  },
  kicker: {
    color: colors.primary,
    fontSize: 14,
    fontWeight: "800",
  },
  title: {
    color: colors.ink,
    fontSize: 28,
    fontWeight: "800",
    lineHeight: 34,
  },
  subtitle: {
    color: colors.muted,
    fontSize: 16,
    lineHeight: 23,
  },
});
