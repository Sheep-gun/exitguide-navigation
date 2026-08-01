import { StyleSheet, Text, View } from "react-native";

import { isExitGuideOverlayAvailable } from "../native/ExitGuideOverlay";
import { colors, radii } from "../styles/theme";
import { ActionButton } from "./ActionButton";

type OverlayControlsProps = {
  hasAccessibility: boolean;
  hasPermission: boolean;
  message: string | null;
  onOpenAccessibilitySettings: () => void;
  onOpenOverlaySettings: () => void;
  onStop: () => void;
  stopDisabled: boolean;
  stopLoading: boolean;
};

export function OverlayControls({
  hasAccessibility,
  hasPermission,
  message,
  onOpenAccessibilitySettings,
  onOpenOverlaySettings,
  onStop,
  stopDisabled,
  stopLoading,
}: OverlayControlsProps) {
  const isReady = hasPermission && hasAccessibility;
  const statusText = isExitGuideOverlayAvailable ? (isReady ? "내비게이션 준비" : "권한 필요") : "APK 전용";

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <View style={styles.headerText}>
          <Text style={styles.eyebrow}>화면 위 분석</Text>
          <Text style={styles.title}>작은 아이콘으로 바로 분석</Text>
        </View>
        <Text style={[styles.statusChip, isReady && styles.statusReady]}>{statusText}</Text>
      </View>
      <Text style={styles.helper}>
        저장된 경로가 있으면 즉시 안내하고, 없으면 안전한 메뉴 클릭과 스크롤로 경로를 탐색합니다. 최종 버튼은 사용자가 직접 누릅니다.
      </Text>
      <View style={styles.buttonStack}>
        <ActionButton onPress={onOpenOverlaySettings} tone="secondary">
          화면 위 표시 권한 열기
        </ActionButton>
        <ActionButton onPress={onOpenAccessibilitySettings} tone="secondary">
          접근성 화면 읽기 권한 열기
        </ActionButton>
        <ActionButton disabled={stopDisabled} loading={stopLoading} onPress={onStop} tone="secondary">
          아이콘 끄기
        </ActionButton>
      </View>
      {message ? <Text style={styles.message}>{message}</Text> : null}
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
  eyebrow: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "900",
  },
  title: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
  },
  statusChip: {
    backgroundColor: "#F2F4F7",
    borderColor: colors.border,
    borderRadius: radii.pill,
    borderWidth: 1,
    color: colors.muted,
    fontSize: 12,
    fontWeight: "900",
    overflow: "hidden",
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  statusReady: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primaryBorder,
    color: colors.primary,
  },
  helper: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 19,
  },
  buttonStack: {
    gap: 8,
  },
  message: {
    color: colors.ink,
    fontSize: 13,
    lineHeight: 19,
  },
});
