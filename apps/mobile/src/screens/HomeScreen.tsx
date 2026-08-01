import { useMemo, useState } from "react";
import { SafeAreaView, ScrollView, StatusBar, StyleSheet, Text, View } from "react-native";
import * as ImagePicker from "expo-image-picker";

import {
  analyzeDemoFlow,
  analyzeDemoScenario,
  analyzeScreenshot,
  analyzeScreenshotFlow,
  fetchPromptPreview,
} from "../api/exitguideApi";
import { ActionButton } from "../components/ActionButton";
import { AnalysisHistory } from "../components/AnalysisHistory";
import { AnalysisResult } from "../components/AnalysisResult";
import { ApiSettings } from "../components/ApiSettings";
import { AppHeader } from "../components/AppHeader";
import { CatalogStatus } from "../components/CatalogStatus";
import { DemoFlowList } from "../components/DemoFlowList";
import { DemoScenarioList } from "../components/DemoScenarioList";
import { EmptyState } from "../components/EmptyState";
import { FlowHistory } from "../components/FlowHistory";
import { FlowScreenshotAnalyzer } from "../components/FlowScreenshotAnalyzer";
import { FlowResult } from "../components/FlowResult";
import { MessagePanel } from "../components/MessagePanel";
import { OverlayControls } from "../components/OverlayControls";
import { ProviderSettings } from "../components/ProviderSettings";
import { PromptPreviewPanel } from "../components/PromptPreviewPanel";
import { PurposeInput } from "../components/PurposeInput";
import { ScreenshotAnalyzer } from "../components/ScreenshotAnalyzer";
import { Section } from "../components/Section";
import { AppTab, SegmentedTabs } from "../components/SegmentedTabs";
import { useAnalysisHistory } from "../hooks/useAnalysisHistory";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { useExitGuideCatalog } from "../hooks/useExitGuideCatalog";
import { useFlowHistory } from "../hooks/useFlowHistory";
import { useExitGuideOverlayController } from "../hooks/useExitGuideOverlayController";
import { useStoredApiBaseUrl } from "../hooks/useStoredApiBaseUrl";
import { useStoredProviderSettings } from "../hooks/useStoredProviderSettings";
import { colors, radii } from "../styles/theme";
import type {
  AnalysisHistoryItem,
  AnalysisResponse,
  DemoFlow,
  DemoScenario,
  FlowAnalysisResponse,
  FlowHistoryItem,
  PromptPreviewResponse,
  SelectedImage,
} from "../types";

export function HomeScreen() {
  const { apiBaseUrl, setApiBaseUrl } = useStoredApiBaseUrl();
  const { providerSettings, setProviderSettings } = useStoredProviderSettings();
  const [activeTab, setActiveTab] = useState<AppTab>("screenshot");
  const [purposeText, setPurposeText] = useState("");
  const [selectedImage, setSelectedImage] = useState<SelectedImage | null>(null);
  const [selectedFlowImages, setSelectedFlowImages] = useState<SelectedImage[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [analysisSource, setAnalysisSource] = useState<string | null>(null);
  const [flowAnalysis, setFlowAnalysis] = useState<FlowAnalysisResponse | null>(null);
  const [flowSource, setFlowSource] = useState<string | null>(null);
  const [promptPreview, setPromptPreview] = useState<PromptPreviewResponse | null>(null);
  const [promptSource, setPromptSource] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const catalogApiBaseUrl = useDebouncedValue(apiBaseUrl, 500);

  const { addHistoryItem, clearHistory, history } = useAnalysisHistory();
  const { addFlowHistoryItem, clearFlows, flowHistory } = useFlowHistory();
  const overlay = useExitGuideOverlayController();
  const {
    apiStatus,
    catalogMessage,
    catalogSource,
    demoQuality,
    demoFlows,
    demoReadiness,
    demoScenarios,
    isCatalogLoading,
  } = useExitGuideCatalog(catalogApiBaseUrl);

  const goalRequest = useMemo(() => {
    const trimmedPurpose = purposeText.trim();
    return trimmedPurpose ? { goalText: trimmedPurpose } : { inferGoal: true };
  }, [purposeText]);
  const apiNeedsAttention = Boolean(
    catalogMessage ||
      demoQuality?.status === "fail" ||
      demoReadiness?.status === "needs_setup" ||
      apiStatus?.provider_ready === false,
  );
  const statusLabel = apiStatus
    ? apiNeedsAttention
      ? "설정 필요"
      : "API 준비"
    : "오프라인";
  const canAnalyzeScreenshot = useMemo(
    () => Boolean(selectedImage && apiBaseUrl.trim()),
    [apiBaseUrl, selectedImage],
  );
  const canAnalyzeScreenshotFlow = useMemo(
    () => Boolean(selectedFlowImages.length >= 2 && apiBaseUrl.trim()),
    [apiBaseUrl, selectedFlowImages],
  );
  function clearOutputs() {
    setAnalysis(null);
    setAnalysisSource(null);
    setFlowAnalysis(null);
    setFlowSource(null);
    setPromptPreview(null);
    setPromptSource(null);
  }

  function clearSelectedMedia() {
    setSelectedImage(null);
    setSelectedFlowImages([]);
  }

  function clearScreenshotSelection() {
    setSelectedImage(null);
    clearOutputs();
    setErrorMessage(null);
  }

  function clearFlowSelection() {
    setSelectedFlowImages([]);
    clearOutputs();
    setErrorMessage(null);
  }

  async function pickScreenshot() {
    setErrorMessage(null);

    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setErrorMessage("사진을 분석하려면 사진 접근 권한이 필요합니다.");
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.95,
    });

    if (!result.canceled) {
      setSelectedImage(result.assets[0]);
      setSelectedFlowImages([]);
      clearOutputs();
    }
  }

  async function pickFlowScreenshots() {
    setErrorMessage(null);

    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setErrorMessage("흐름을 분석하려면 사진 접근 권한이 필요합니다.");
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      allowsMultipleSelection: true,
      mediaTypes: ["images"],
      orderedSelection: true,
      quality: 0.95,
      selectionLimit: 6,
    });

    if (!result.canceled) {
      setSelectedFlowImages(result.assets.slice(0, 6));
      setSelectedImage(null);
      clearOutputs();
    }
  }

  async function submitScreenshot() {
    if (!selectedImage) {
      setErrorMessage("먼저 사진을 선택하세요.");
      return;
    }

    await runAnalysis("사진 업로드", () =>
      analyzeScreenshot({
        apiBaseUrl,
        providerSettings,
        ...goalRequest,
        image: selectedImage,
      }),
    );
  }

  async function submitScreenshotFlow() {
    if (selectedFlowImages.length < 2) {
      setErrorMessage("흐름 분석에는 최소 2장의 사진이 필요합니다.");
      return;
    }

    clearOutputs();
    setIsAnalyzing(true);
    setErrorMessage(null);

    try {
      const data = await analyzeScreenshotFlow({
        apiBaseUrl,
        providerSettings,
        ...goalRequest,
        images: selectedFlowImages,
      });
      setFlowAnalysis(data);
      setFlowSource("사진 흐름 업로드");
      addFlowHistoryItem(data, "사진 흐름 업로드");
    } catch (error) {
      const message = error instanceof Error ? error.message : "흐름 분석에 실패했습니다.";
      setErrorMessage(message);
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function runDemo(scenario: DemoScenario) {
    clearSelectedMedia();
    clearOutputs();
    setIsAnalyzing(true);
    setErrorMessage(null);

    try {
      const [data, prompt] = await Promise.all([
        analyzeDemoScenario({
          apiBaseUrl,
          providerSettings,
          ...goalRequest,
          scenarioId: scenario.id,
        }),
        fetchPromptPreview({
          apiBaseUrl,
          providerSettings,
          ...goalRequest,
          scenarioId: scenario.id,
        }),
      ]);
      setAnalysis(data);
      setAnalysisSource(`데모: ${scenario.title}`);
      setPromptPreview(prompt);
      setPromptSource(`데모: ${scenario.title}`);
      addHistoryItem(data, `데모: ${scenario.title}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "분석에 실패했습니다.";
      setErrorMessage(message);
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function runFlow(flow: DemoFlow) {
    clearSelectedMedia();
    clearOutputs();
    setIsAnalyzing(true);
    setErrorMessage(null);

    try {
      const data = await analyzeDemoFlow({
        apiBaseUrl,
        providerSettings,
        ...goalRequest,
        scenarioIds: flow.scenarioIds,
      });
      setFlowAnalysis(data);
      setFlowSource(`흐름: ${flow.title}`);
      addFlowHistoryItem(data, `흐름: ${flow.title}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "흐름 분석에 실패했습니다.";
      setErrorMessage(message);
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function runAnalysis(sourceLabel: string, task: () => Promise<AnalysisResponse>) {
    clearOutputs();
    setIsAnalyzing(true);
    setErrorMessage(null);

    try {
      const data = await task();
      setAnalysis(data);
      setAnalysisSource(sourceLabel);
      addHistoryItem(data, sourceLabel);
    } catch (error) {
      const message = error instanceof Error ? error.message : "분석에 실패했습니다.";
      setErrorMessage(message);
    } finally {
      setIsAnalyzing(false);
    }
  }

  function openAnalysisHistoryItem(item: AnalysisHistoryItem) {
    clearOutputs();
    clearSelectedMedia();
    setAnalysis(item.analysis);
    setAnalysisSource(item.sourceLabel);
    setActiveTab("history");
    setErrorMessage(null);
  }

  function openFlowHistoryItem(item: FlowHistoryItem) {
    clearOutputs();
    clearSelectedMedia();
    setFlowAnalysis(item.flow);
    setFlowSource(item.sourceLabel);
    setActiveTab("history");
    setErrorMessage(null);
  }

  function renderTabContent() {
    if (activeTab === "demo") {
      return (
        <Section title="데모 시나리오">
          <DemoScenarioList busy={isAnalyzing} onRun={runDemo} scenarios={demoScenarios} />
        </Section>
      );
    }

    if (activeTab === "screenshot") {
      return (
        <Section title="사진 분석">
          <ScreenshotAnalyzer
            canAnalyze={canAnalyzeScreenshot}
            isAnalyzing={isAnalyzing}
            onAnalyze={submitScreenshot}
            onClear={clearScreenshotSelection}
            onPick={pickScreenshot}
            selectedImage={selectedImage}
          />
        </Section>
      );
    }

    if (activeTab === "flow") {
      return (
        <View style={styles.tabStack}>
          <Section title="사진 흐름">
            <FlowScreenshotAnalyzer
              canAnalyze={canAnalyzeScreenshotFlow}
              images={selectedFlowImages}
              isAnalyzing={isAnalyzing}
              onAnalyze={submitScreenshotFlow}
              onClear={clearFlowSelection}
              onPick={pickFlowScreenshots}
            />
          </Section>
          <Section title="흐름 데모">
            <DemoFlowList busy={isAnalyzing} flows={demoFlows} onRun={runFlow} />
          </Section>
        </View>
      );
    }

    return (
      <View style={styles.tabStack}>
        <Section title="최근 단일 분석">
          {history.length ? (
            <AnalysisHistory items={history} onClear={clearHistory} onOpen={openAnalysisHistoryItem} />
          ) : (
            <EmptyState
              title="저장된 단일 분석이 없습니다"
              message="데모나 사진 분석을 실행하면 이곳에 최근 결과가 저장됩니다."
            />
          )}
        </Section>
        <Section title="최근 흐름 분석">
          {flowHistory.length ? (
            <FlowHistory items={flowHistory} onClear={clearFlows} onOpen={openFlowHistoryItem} />
          ) : (
            <EmptyState
              title="저장된 흐름 분석이 없습니다"
              message="흐름 데모나 여러 장의 사진 분석을 실행하면 이곳에 저장됩니다."
            />
          )}
        </Section>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="dark-content" />
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.headerBar}>
          <AppHeader />
          <View style={[styles.statusChip, apiNeedsAttention && styles.statusChipWarning]}>
            <Text style={[styles.statusText, apiNeedsAttention && styles.statusTextWarning]}>
              {statusLabel}
            </Text>
            {isCatalogLoading ? <Text style={styles.statusSubtext}>확인 중</Text> : null}
          </View>
        </View>

        <PurposeInput
          onChange={setPurposeText}
          onClear={() => void overlay.clearNavigation()}
          onStart={() => void overlay.startNavigation(apiBaseUrl, purposeText, providerSettings)}
          startDisabled={!apiBaseUrl.trim()}
          startLoading={overlay.startBusy}
          value={purposeText}
        />

        <OverlayControls
          hasAccessibility={overlay.hasAccessibility}
          hasPermission={overlay.hasPermission}
          message={overlay.message}
          onOpenAccessibilitySettings={() => void overlay.openAccessibilitySettings()}
          onOpenOverlaySettings={() => void overlay.openOverlaySettings()}
          onStop={() => void overlay.stopNavigation()}
          stopDisabled={false}
          stopLoading={overlay.stopBusy}
        />

        <Section title="AI/API 설정">
          <View style={styles.settingsStack}>
            <ApiSettings apiBaseUrl={apiBaseUrl} onChange={setApiBaseUrl} />
            <ProviderSettings settings={providerSettings} onChange={setProviderSettings} />
          </View>
          {apiNeedsAttention ? (
            <CatalogStatus
              apiStatus={apiStatus}
              catalogMessage={catalogMessage}
              catalogSource={catalogSource}
              demoQuality={demoQuality}
              demoReadiness={demoReadiness}
              isLoading={isCatalogLoading}
            />
          ) : null}
        </Section>

        <SegmentedTabs activeTab={activeTab} onChange={setActiveTab} />
        {renderTabContent()}

        {errorMessage ? <MessagePanel message={errorMessage} title="먼저 확인하세요" /> : null}

        {analysis ? <AnalysisResult analysis={analysis} sourceLabel={analysisSource} /> : null}
        {flowAnalysis ? <FlowResult flow={flowAnalysis} sourceLabel={flowSource} /> : null}
        {promptPreview ? <PromptPreviewPanel preview={promptPreview} sourceLabel={promptSource} /> : null}

        {analysis || flowAnalysis ? (
          <ActionButton
            onPress={() => {
              clearOutputs();
              setErrorMessage(null);
            }}
            tone="secondary"
          >
            결과 지우기
          </ActionButton>
        ) : null}

      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: colors.background,
    flex: 1,
  },
  container: {
    gap: 18,
    padding: 18,
    paddingBottom: 40,
  },
  headerBar: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
    paddingTop: 16,
  },
  statusChip: {
    alignSelf: "flex-end",
    backgroundColor: colors.primarySoft,
    borderColor: colors.primaryBorder,
    borderRadius: radii.pill,
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 11,
    paddingVertical: 6,
  },
  statusChipWarning: {
    backgroundColor: "#FFF4E5",
    borderColor: "#F5CA8A",
  },
  statusText: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "900",
  },
  statusTextWarning: {
    color: "#9A5A00",
  },
  statusSubtext: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  settingsStack: {
    gap: 12,
  },
  tabStack: {
    gap: 20,
  },
});
