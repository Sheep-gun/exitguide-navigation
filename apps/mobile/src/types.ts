import type * as ImagePicker from "expo-image-picker";

export type Goal = {
  id: string;
  title: string;
  description: string;
};

export type DemoScenario = {
  id: string;
  title: string;
  description: string;
  recommendedGoalId: string;
  fixtureFilename?: string;
};

export type DemoFlow = {
  id: string;
  title: string;
  description: string;
  goalId: string;
  scenarioIds: string[];
};

export type RiskLevel = "low" | "medium" | "high";

export type ApiStatus = {
  status: string;
  ocr_provider: string;
  llm_provider: string;
  provider_ready?: boolean;
  provider_notes?: string[];
  supported_ai_providers?: AiProviderId[];
};

export type AiProviderId = "server" | "google" | "gpt" | "exaone";

export type AiProviderSettings = {
  providerId: AiProviderId;
  apiKey: string;
  model: string;
  baseUrl: string;
};

export type ApiProviderOption = {
  id: AiProviderId;
  label: string;
  model: string;
  base_url: string;
  ready: boolean;
};

export type ReadinessCheck = {
  id: string;
  label: string;
  passed: boolean;
  detail: string;
};

export type DemoReadiness = {
  status: "ready" | "needs_setup";
  checks: ReadinessCheck[];
};

export type DemoQualitySummary = {
  readiness_passed: number;
  readiness_total: number;
  scenarios_passed: number;
  scenarios_total: number;
  flows_passed: number;
  flows_total: number;
  synthetic_passed: number;
  synthetic_total: number;
};

export type DemoQualityCalibration = {
  id: string;
  label: string;
  source: "scenario" | "synthetic";
  goal_id: string;
  expected_risk: RiskLevel | null;
  actual_risk: RiskLevel | null;
  alignment_score: number | null;
  passed: boolean;
  detail: string;
};

export type DemoQualityFlowCalibration = {
  id: string;
  label: string;
  goal_id: string;
  expected_overall_risk: RiskLevel | null;
  actual_overall_risk: RiskLevel | null;
  expected_risk_path: RiskLevel[];
  actual_risk_path: RiskLevel[];
  alignment_score: number | null;
  passed: boolean;
  detail: string;
};

export type DemoQuality = {
  status: "pass" | "fail";
  summary: DemoQualitySummary;
  checks: ReadinessCheck[];
  scenario_calibrations: DemoQualityCalibration[];
  flow_calibrations: DemoQualityFlowCalibration[];
  synthetic_calibrations: DemoQualityCalibration[];
};

export type PromptPreviewResponse = {
  goal_id: string;
  scenario_id: string;
  system_prompt: string;
  user_prompt: string;
};

export type GoalDefinition = {
  id: string;
  label: string;
  description?: string;
};

export type DemoScenarioDefinition = {
  id: string;
  label: string;
  description: string;
  recommended_goal_id: string;
  fixture_filename: string;
};

export type DemoFlowDefinition = {
  id: string;
  label: string;
  description: string;
  goal_id: string;
  scenario_ids: string[];
};

export type UiElement = {
  id: string;
  label: string;
  element_type: string;
  direction: "supports_goal" | "conflicts_with_goal" | "needs_check";
  risk_level: RiskLevel;
  reason: string;
  signals?: string[];
};

export type AnalysisResponse = {
  analysis_id?: string;
  goal_id: string;
  goal_label: string;
  screen_title: string;
  analysis_mode: "demo" | "upload";
  overall_risk: RiskLevel;
  alignment_score: number;
  risk_counts: {
    low: number;
    medium: number;
    high: number;
  };
  summary: string;
  elements: UiElement[];
  recommended_action: {
    title: string;
    description: string;
    target_element_id: string | null;
  };
  proof_card: ProofCard;
};

export type FlowAnalysisResponse = {
  flow_id?: string;
  goal_id: string;
  goal_label: string;
  overall_risk: RiskLevel;
  alignment_score: number;
  screen_count: number;
  highest_risk_screen_number: number | null;
  risk_counts: {
    low: number;
    medium: number;
    high: number;
  };
  risk_path?: RiskLevel[];
  summary: string;
  screens: AnalysisResponse[];
  proof_card: ProofCard;
};

export type ProofCard = {
  goal: string;
  summary: string;
  key_evidence: string[];
  disclaimer: string;
};

export type AnalysisHistoryItem = {
  id: string;
  createdAt: string;
  sourceLabel: string | null;
  analysis: AnalysisResponse;
};

export type FlowHistoryItem = {
  id: string;
  createdAt: string;
  sourceLabel: string | null;
  flow: FlowAnalysisResponse;
};

export type SelectedImage = ImagePicker.ImagePickerAsset;
