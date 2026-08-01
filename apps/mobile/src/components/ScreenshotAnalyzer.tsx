import { Image, StyleSheet, Text, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { SelectedImage } from "../types";
import { ActionButton } from "./ActionButton";

type ScreenshotAnalyzerProps = {
  canAnalyze: boolean;
  isAnalyzing: boolean;
  onAnalyze: () => void;
  onClear: () => void;
  onPick: () => void;
  selectedImage: SelectedImage | null;
};

export function ScreenshotAnalyzer({
  canAnalyze,
  isAnalyzing,
  onAnalyze,
  onClear,
  onPick,
  selectedImage,
}: ScreenshotAnalyzerProps) {
  return (
    <View style={styles.wrap}>
      <ActionButton onPress={onPick} tone="secondary">
        {selectedImage ? "다른 사진 선택" : "사진 선택"}
      </ActionButton>

      {selectedImage ? (
        <View style={styles.previewRow}>
          <Image source={{ uri: selectedImage.uri }} style={styles.previewImage} />
          <View style={styles.previewTextWrap}>
            <Text style={styles.previewTitle}>{selectedImage.fileName ?? "선택한 이미지"}</Text>
            <Text style={styles.previewMeta}>
              {selectedImage.width} x {selectedImage.height}
            </Text>
            <Text accessibilityRole="button" onPress={onClear} style={styles.clearText}>
              선택 지우기
            </Text>
          </View>
        </View>
      ) : null}

      <ActionButton disabled={!canAnalyze} loading={isAnalyzing} onPress={onAnalyze}>
        사진 분석하기
      </ActionButton>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 12,
  },
  previewRow: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.card,
    borderWidth: 1,
    flexDirection: "row",
    gap: 12,
    padding: 12,
  },
  previewImage: {
    backgroundColor: "#E8ECF2",
    borderRadius: radii.preview,
    height: 72,
    width: 72,
  },
  previewTextWrap: {
    flex: 1,
    gap: 4,
  },
  previewTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "800",
  },
  previewMeta: {
    color: colors.muted,
    fontSize: 13,
  },
  clearText: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "800",
  },
});
