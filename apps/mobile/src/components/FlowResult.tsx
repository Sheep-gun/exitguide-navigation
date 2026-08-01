import { StyleSheet, Text, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { FlowAnalysisResponse } from "../types";
import { riskLabel } from "../utils/labels";
import { ProofCard } from "./ProofCard";
import { RiskBadge } from "./RiskBadge";

type FlowResultProps = {
  flow: FlowAnalysisResponse;
  sourceLabel: string | null;
};

export function FlowResult({ flow, sourceLabel }: FlowResultProps) {
  const metadata = [sourceLabel ?? "데모 흐름", flow.flow_id ? `ID ${flow.flow_id}` : null]
    .filter((value): value is string => Boolean(value))
    .join(" | ");

  return (
    <View style={styles.wrap}>
      <View style={styles.header}>
        <View style={styles.headerText}>
          <Text style={styles.title}>흐름 분석</Text>
          <Text style={styles.meta}>{metadata}</Text>
        </View>
        <RiskBadge risk={flow.overall_risk} />
      </View>
      <ProofCard proofCard={flow.proof_card} traceId={flow.flow_id} />
      <View style={styles.card}>
        <Text style={styles.score}>목표 일치도 {flow.alignment_score}/100</Text>
        <Text style={styles.counts}>
          높음 {flow.risk_counts.high} | 주의 {flow.risk_counts.medium} | 낮음 {flow.risk_counts.low}
        </Text>
        <Text style={styles.counts}>
          {flow.screen_count}개 화면 | 가장 위험한 화면 {flow.highest_risk_screen_number ?? "없음"}
        </Text>
        {flow.risk_path?.length ? (
          <Text style={styles.path}>위험 경로 {flow.risk_path.map(riskLabel).join(" > ")}</Text>
        ) : null}
        <Text style={styles.summary}>{flow.summary}</Text>
        {flow.screens.map((screen, index) => (
          <Text key={`${screen.screen_title}-${index}`} style={styles.screenLine}>
            {index + 1}. {screen.screen_title} | {riskLabel(screen.overall_risk)} | {screen.alignment_score}/100
          </Text>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 14,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  headerText: {
    flex: 1,
  },
  title: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
  },
  meta: {
    color: colors.muted,
    fontSize: 13,
    marginTop: 3,
  },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.card,
    borderWidth: 1,
    gap: 8,
    padding: 14,
  },
  score: {
    color: colors.primary,
    fontSize: 15,
    fontWeight: "800",
  },
  counts: {
    color: colors.muted,
    fontSize: 12,
  },
  path: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "800",
  },
  summary: {
    color: "#3F4650",
    fontSize: 14,
    lineHeight: 20,
  },
  screenLine: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 19,
  },
});
