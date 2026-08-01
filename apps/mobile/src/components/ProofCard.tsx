import { Share, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { ProofCard as ProofCardType } from "../types";

type ProofCardProps = {
  proofCard: ProofCardType;
  traceId?: string | null;
};

export function ProofCard({ proofCard, traceId }: ProofCardProps) {
  async function shareProofCard() {
    try {
      await Share.share({
        message: formatProofCard(proofCard, traceId),
        title: "ExitGuide 근거 카드",
      });
    } catch (error) {
      console.warn("Proof Card share failed", error);
    }
  }

  return (
    <View style={styles.card}>
      <Text style={styles.label}>근거 카드</Text>
      <Text style={styles.title}>{proofCard.goal}</Text>
      {traceId ? <Text style={styles.traceId}>추적 ID {traceId}</Text> : null}
      <Text style={styles.summary}>{proofCard.summary}</Text>
      {proofCard.key_evidence.map((evidence) => (
        <Text key={evidence} style={styles.evidence}>
          - {evidence}
        </Text>
      ))}
      <TouchableOpacity accessibilityRole="button" onPress={shareProofCard} style={styles.shareButton}>
        <Text style={styles.shareText}>근거 카드 공유</Text>
      </TouchableOpacity>
      <Text style={styles.disclaimer}>{proofCard.disclaimer}</Text>
    </View>
  );
}

function formatProofCard(proofCard: ProofCardType, traceId?: string | null): string {
  return [
    `ExitGuide 근거 카드: ${proofCard.goal}`,
    traceId ? `추적 ID: ${traceId}` : null,
    proofCard.summary,
    "",
    "근거:",
    ...proofCard.key_evidence.map((evidence) => `- ${evidence}`),
    "",
    proofCard.disclaimer,
  ].filter((line): line is string => line !== null).join("\n");
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.card,
    borderWidth: 1,
    gap: 8,
    padding: 16,
  },
  label: {
    color: colors.violet,
    fontSize: 13,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  title: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
  },
  summary: {
    color: "#3F4650",
    fontSize: 14,
    lineHeight: 21,
  },
  traceId: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  evidence: {
    color: "#3F4650",
    fontSize: 14,
    lineHeight: 20,
  },
  shareButton: {
    alignItems: "center",
    borderColor: colors.violet,
    borderRadius: radii.control,
    borderWidth: 1,
    marginTop: 4,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  shareText: {
    color: colors.violet,
    fontSize: 13,
    fontWeight: "800",
  },
  disclaimer: {
    color: "#6A737D",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 4,
  },
});
