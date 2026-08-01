import { StyleSheet, Text, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { PromptPreviewResponse } from "../types";

type PromptPreviewPanelProps = {
  preview: PromptPreviewResponse;
  sourceLabel: string | null;
};

const USER_PROMPT_PREVIEW_LENGTH = 900;

export function PromptPreviewPanel({ preview, sourceLabel }: PromptPreviewPanelProps) {
  const clippedUserPrompt =
    preview.user_prompt.length > USER_PROMPT_PREVIEW_LENGTH
      ? `${preview.user_prompt.slice(0, USER_PROMPT_PREVIEW_LENGTH)}...`
      : preview.user_prompt;

  return (
    <View style={styles.card}>
      <Text style={styles.label}>프롬프트 미리보기</Text>
      <Text style={styles.title}>{sourceLabel ?? preview.scenario_id}</Text>
      <Text style={styles.meta}>
        시스템 {preview.system_prompt.length}자 | 사용자 {preview.user_prompt.length}자
      </Text>
      <Text selectable style={styles.promptText}>
        {clippedUserPrompt}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#111827",
    borderRadius: radii.card,
    gap: 8,
    padding: 16,
  },
  label: {
    color: "#A7F3D0",
    fontSize: 12,
    fontWeight: "900",
    textTransform: "uppercase",
  },
  title: {
    color: colors.surface,
    fontSize: 16,
    fontWeight: "800",
  },
  meta: {
    color: "#CBD5E1",
    fontSize: 12,
  },
  promptText: {
    color: "#E5E7EB",
    fontFamily: "monospace",
    fontSize: 11,
    lineHeight: 17,
  },
});
