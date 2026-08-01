import { Image, StyleSheet, Text, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { SelectedImage } from "../types";
import { ActionButton } from "./ActionButton";

type FlowScreenshotAnalyzerProps = {
  canAnalyze: boolean;
  images: SelectedImage[];
  isAnalyzing: boolean;
  onAnalyze: () => void;
  onClear: () => void;
  onPick: () => void;
};

export function FlowScreenshotAnalyzer({
  canAnalyze,
  images,
  isAnalyzing,
  onAnalyze,
  onClear,
  onPick,
}: FlowScreenshotAnalyzerProps) {
  return (
    <View style={styles.wrap}>
      <ActionButton onPress={onPick} tone="secondary">
        {images.length ? "다른 흐름 사진 선택" : "흐름 사진 선택"}
      </ActionButton>

      {images.length ? (
        <View style={styles.previewCard}>
          <Text style={styles.previewTitle}>{images.length}개 화면 선택됨</Text>
          <View style={styles.thumbnailRow}>
            {images.slice(0, 4).map((image, index) => (
              <View key={`${image.uri}-${index}`} style={styles.thumbnailWrap}>
                <Image source={{ uri: image.uri }} style={styles.thumbnail} />
                <Text style={styles.index}>{index + 1}</Text>
              </View>
            ))}
            {images.length > 4 ? (
              <View style={styles.moreThumb}>
                <Text style={styles.moreText}>+{images.length - 4}</Text>
              </View>
            ) : null}
          </View>
          <Text style={styles.helper}>
            사용자가 본 순서대로 2-6장 선택하세요.
          </Text>
          <Text accessibilityRole="button" onPress={onClear} style={styles.clearText}>
            흐름 지우기
          </Text>
        </View>
      ) : null}

      <ActionButton disabled={!canAnalyze} loading={isAnalyzing} onPress={onAnalyze}>
        흐름 분석하기
      </ActionButton>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 12,
  },
  previewCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.card,
    borderWidth: 1,
    gap: 10,
    padding: 12,
  },
  previewTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "800",
  },
  thumbnailRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  thumbnailWrap: {
    position: "relative",
  },
  thumbnail: {
    backgroundColor: "#E8ECF2",
    borderRadius: radii.preview,
    height: 64,
    width: 64,
  },
  index: {
    backgroundColor: colors.ink,
    borderRadius: radii.pill,
    color: colors.surface,
    fontSize: 11,
    fontWeight: "800",
    minWidth: 20,
    overflow: "hidden",
    paddingHorizontal: 5,
    paddingVertical: 2,
    position: "absolute",
    right: 4,
    textAlign: "center",
    top: 4,
  },
  moreThumb: {
    alignItems: "center",
    backgroundColor: "#E8ECF2",
    borderRadius: radii.preview,
    height: 64,
    justifyContent: "center",
    width: 64,
  },
  moreText: {
    color: colors.primary,
    fontSize: 14,
    fontWeight: "800",
  },
  helper: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 17,
  },
  clearText: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "800",
  },
});
