import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { colors, radii } from "../styles/theme";
import type { ApiStatus, DemoQuality, DemoReadiness } from "../types";

type CatalogStatusProps = {
  apiStatus: ApiStatus | null;
  catalogMessage: string | null;
  catalogSource: "api" | "fallback";
  demoQuality: DemoQuality | null;
  demoReadiness: DemoReadiness | null;
  isLoading: boolean;
};

export function CatalogStatus({
  apiStatus,
  catalogMessage,
  catalogSource,
  demoQuality,
  demoReadiness,
  isLoading,
}: CatalogStatusProps) {
  const title = apiStatus
    ? demoQuality?.status === "fail"
      ? "검증 점검 필요"
      : demoReadiness?.status === "needs_setup" || apiStatus.provider_ready === false
      ? "Provider 설정 필요"
      : "API 준비 완료"
    : catalogSource === "api"
      ? "실시간 카탈로그 연결됨"
      : "내장 카탈로그 사용 중";
  const failedChecks = demoReadiness?.checks.filter((check) => !check.passed) ?? [];

  return (
    <View style={styles.panel}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>{title}</Text>
        {isLoading ? <ActivityIndicator color={colors.primary} size="small" /> : null}
      </View>
      {apiStatus ? (
        <View style={styles.detailList}>
          <Text style={styles.body}>
            API 정상 | OCR {apiStatus.ocr_provider} | LLM {apiStatus.llm_provider}
          </Text>
          {demoQuality ? (
            <Text style={styles.body}>
              검증 {demoQuality.status} | 데모 {demoQuality.summary.scenarios_passed}/
              {demoQuality.summary.scenarios_total} | 흐름 {demoQuality.summary.flows_passed}/
              {demoQuality.summary.flows_total} | 합성 {demoQuality.summary.synthetic_passed}/
              {demoQuality.summary.synthetic_total}
            </Text>
          ) : null}
          {apiStatus.provider_notes?.slice(0, 2).map((note) => (
            <Text key={note} style={styles.note}>
              - {note}
            </Text>
          ))}
          {demoReadiness ? (
            <View style={styles.chipRow}>
              {demoReadiness.checks.map((check) => (
                <Text key={check.id} style={[styles.chip, !check.passed && styles.chipWarning]}>
                  {check.passed ? "정상" : "설정"} {check.label}
                </Text>
              ))}
            </View>
          ) : null}
          {failedChecks.length ? (
            <View style={styles.issueList}>
              {failedChecks.slice(0, 3).map((check) => (
                <Text key={check.id} style={styles.issueText}>
                  {check.label}: {check.detail}
                </Text>
              ))}
            </View>
          ) : null}
        </View>
      ) : (
        <Text style={styles.body}>{catalogMessage ?? "오프라인 내장 데모를 사용할 수 있습니다."}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.card,
    borderWidth: 1,
    gap: 5,
    padding: 12,
  },
  headerRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  title: {
    color: colors.ink,
    flex: 1,
    fontSize: 14,
    fontWeight: "800",
  },
  body: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 18,
  },
  detailList: {
    gap: 4,
  },
  note: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 17,
  },
  chipRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    paddingTop: 2,
  },
  chip: {
    backgroundColor: "#EAF5F2",
    borderColor: "#B8DCD4",
    borderRadius: 999,
    borderWidth: 1,
    color: colors.primary,
    fontSize: 11,
    fontWeight: "800",
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  chipWarning: {
    backgroundColor: "#FFF4E5",
    borderColor: "#F5CA8A",
    color: "#9A5A00",
  },
  issueList: {
    borderLeftColor: colors.warning,
    borderLeftWidth: 3,
    gap: 4,
    marginTop: 2,
    paddingLeft: 9,
  },
  issueText: {
    color: "#7A4A00",
    fontSize: 12,
    lineHeight: 17,
  },
});
