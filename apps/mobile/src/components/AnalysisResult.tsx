import { StyleSheet, Text, View } from "react-native";

import { colors } from "../styles/theme";
import type { AnalysisResponse } from "../types";
import { modeLabel } from "../utils/labels";
import { AlignmentMeter } from "./AlignmentMeter";
import { ProofCard } from "./ProofCard";
import { RecommendedActionCard } from "./RecommendedActionCard";
import { RiskBadge } from "./RiskBadge";
import { RiskLegend } from "./RiskLegend";
import { UiElementCard } from "./UiElementCard";

type AnalysisResultProps = {
  analysis: AnalysisResponse;
  sourceLabel: string | null;
};

export function AnalysisResult({ analysis, sourceLabel }: AnalysisResultProps) {
  const metadata = [
    sourceLabel,
    analysis.screen_title,
    modeLabel(analysis.analysis_mode),
    analysis.analysis_id ? `ID ${analysis.analysis_id}` : null,
  ]
    .filter((value): value is string => Boolean(value))
    .join(" | ");

  return (
    <View style={styles.results}>
      <View style={styles.resultHeader}>
        <View style={styles.headerText}>
          <Text style={styles.sectionTitle}>분석 결과</Text>
          <Text style={styles.sourceLabel}>{metadata}</Text>
        </View>
        <RiskBadge risk={analysis.overall_risk} />
      </View>
      <Text style={styles.summary}>{analysis.summary}</Text>

      <ProofCard proofCard={analysis.proof_card} traceId={analysis.analysis_id} />
      <AlignmentMeter analysis={analysis} />
      <RecommendedActionCard action={analysis.recommended_action} />
      <RiskLegend />

      <View style={styles.elementList}>
        {analysis.elements.map((element) => (
          <UiElementCard
            element={element}
            key={element.id}
            recommendedTargetId={analysis.recommended_action.target_element_id}
          />
        ))}
      </View>

    </View>
  );
}

const styles = StyleSheet.create({
  results: {
    gap: 14,
  },
  resultHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  headerText: {
    flex: 1,
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
  },
  sourceLabel: {
    color: colors.muted,
    fontSize: 13,
    marginTop: 3,
  },
  summary: {
    color: "#3F4650",
    fontSize: 15,
    lineHeight: 22,
  },
  elementList: {
    gap: 10,
  },
});
