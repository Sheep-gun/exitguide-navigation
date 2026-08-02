import Constants from "expo-constants";

import type {
  AnalysisResponse,
  ApiStatus,
  ApiProviderOption,
  AiProviderSettings,
  DemoFlowDefinition,
  DemoQuality,
  DemoScenarioDefinition,
  DemoReadiness,
  FlowAnalysisResponse,
  GoalDefinition,
  PromptPreviewResponse,
  SelectedImage,
} from "../types";

export const API_PORT = 8010;
export const DEFAULT_API_BASE_URL = getDefaultApiBaseUrl();
const REQUEST_TIMEOUT_MS = 45000;
const RUNTIME_CONFIG_TIMEOUT_MS = 7000;

type MobileRuntimeConfig = {
  schema_version: number;
  active: boolean;
  api_base_url: string;
};

export type NavigationGoldRecording = {
  recording_id: string;
  status: "recording" | "review_pending" | "human_gold" | "rejected" | "cancelled";
  app_package: string;
  app_version: string;
  locale: string;
  goal_text: string;
  target_function: string;
  step_count: number;
  selected_step_count: number;
  destination_screen_fingerprint: string | null;
  destination_correct: boolean | null;
  safe_stop: boolean | null;
  reviewer: string | null;
  review_notes: string | null;
};

type AnalyzeScreenshotInput = {
  apiBaseUrl: string;
  providerSettings?: AiProviderSettings;
  goalId?: string;
  goalText?: string;
  inferGoal?: boolean;
  image: SelectedImage;
};

type AnalyzeScreenshotFlowInput = {
  apiBaseUrl: string;
  providerSettings?: AiProviderSettings;
  goalId?: string;
  goalText?: string;
  inferGoal?: boolean;
  images: SelectedImage[];
};

type AnalyzeDemoInput = {
  apiBaseUrl: string;
  providerSettings?: AiProviderSettings;
  goalId?: string;
  goalText?: string;
  inferGoal?: boolean;
  scenarioId: string;
};

type AnalyzeDemoFlowInput = {
  apiBaseUrl: string;
  providerSettings?: AiProviderSettings;
  goalId?: string;
  goalText?: string;
  inferGoal?: boolean;
  scenarioIds: string[];
};

export class ExitGuideApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ExitGuideApiError";
  }
}

export async function fetchApiStatus(apiBaseUrl: string): Promise<ApiStatus> {
  return requestJson<ApiStatus>(`${normalizeApiBaseUrl(apiBaseUrl)}/v1/status`);
}

export async function completeNavigationGoldRecording(
  apiBaseUrl: string,
  recordingId: string,
): Promise<NavigationGoldRecording> {
  return requestJson<NavigationGoldRecording>(
    `${normalizeApiBaseUrl(apiBaseUrl)}/v1/navigation/gold/recordings/${encodeURIComponent(recordingId)}/complete`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        destination_correct: true,
        safe_stop: true,
        reviewer: "device_user",
      }),
    },
  );
}

export async function cancelNavigationGoldRecording(
  apiBaseUrl: string,
  recordingId: string,
): Promise<NavigationGoldRecording> {
  return requestJson<NavigationGoldRecording>(
    `${normalizeApiBaseUrl(apiBaseUrl)}/v1/navigation/gold/recordings/${encodeURIComponent(recordingId)}/cancel`,
    { method: "POST" },
  );
}

export async function fetchReadiness(apiBaseUrl: string): Promise<DemoReadiness> {
  return requestJson<DemoReadiness>(`${normalizeApiBaseUrl(apiBaseUrl)}/v1/readiness`);
}

export async function fetchDemoQuality(apiBaseUrl: string): Promise<DemoQuality> {
  return requestJson<DemoQuality>(`${normalizeApiBaseUrl(apiBaseUrl)}/v1/demo-quality`);
}

export async function fetchProviderOptions(apiBaseUrl: string): Promise<ApiProviderOption[]> {
  return requestJson<ApiProviderOption[]>(`${normalizeApiBaseUrl(apiBaseUrl)}/v1/providers`);
}

export async function fetchGoals(apiBaseUrl: string): Promise<GoalDefinition[]> {
  return requestJson<GoalDefinition[]>(`${normalizeApiBaseUrl(apiBaseUrl)}/v1/goals`);
}

export async function fetchDemoScenarios(apiBaseUrl: string): Promise<DemoScenarioDefinition[]> {
  return requestJson<DemoScenarioDefinition[]>(`${normalizeApiBaseUrl(apiBaseUrl)}/v1/demo-scenarios`);
}

export async function fetchDemoFlows(apiBaseUrl: string): Promise<DemoFlowDefinition[]> {
  return requestJson<DemoFlowDefinition[]>(`${normalizeApiBaseUrl(apiBaseUrl)}/v1/demo-flows`);
}

export async function analyzeScreenshot({
  apiBaseUrl,
  providerSettings,
  goalId,
  goalText,
  inferGoal,
  image,
}: AnalyzeScreenshotInput): Promise<AnalysisResponse> {
  const formData = new FormData();
  appendGoalFormData(formData, { goalId, goalText, inferGoal });
  appendProviderFormData(formData, providerSettings);
  formData.append(
    "screenshot",
    {
      uri: image.uri,
      name: image.fileName ?? "screenshot.jpg",
      type: image.mimeType ?? "image/jpeg",
    } as unknown as Blob,
  );

  return requestJson<AnalysisResponse>(`${normalizeApiBaseUrl(apiBaseUrl)}/v1/analyze`, {
    method: "POST",
    body: formData,
  });
}

export async function analyzeScreenshotFlow({
  apiBaseUrl,
  providerSettings,
  goalId,
  goalText,
  inferGoal,
  images,
}: AnalyzeScreenshotFlowInput): Promise<FlowAnalysisResponse> {
  const formData = new FormData();
  appendGoalFormData(formData, { goalId, goalText, inferGoal });
  appendProviderFormData(formData, providerSettings);
  images.forEach((image, index) => {
    formData.append(
      "screenshots",
      {
        uri: image.uri,
        name: image.fileName ?? `flow-screen-${index + 1}.jpg`,
        type: image.mimeType ?? "image/jpeg",
      } as unknown as Blob,
    );
  });

  return requestJson<FlowAnalysisResponse>(`${normalizeApiBaseUrl(apiBaseUrl)}/v1/analyze/flow/upload`, {
    method: "POST",
    body: formData,
  });
}

export async function analyzeDemoScenario({
  apiBaseUrl,
  providerSettings,
  goalId,
  goalText,
  inferGoal,
  scenarioId,
}: AnalyzeDemoInput): Promise<AnalysisResponse> {
  return requestJson<AnalysisResponse>(`${normalizeApiBaseUrl(apiBaseUrl)}/v1/analyze/demo`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ...buildProviderPayload(providerSettings),
      ...buildGoalPayload({ goalId, goalText, inferGoal }),
      scenario_id: scenarioId,
    }),
  });
}

export async function fetchPromptPreview({
  apiBaseUrl,
  providerSettings,
  goalId,
  goalText,
  inferGoal,
  scenarioId,
}: AnalyzeDemoInput): Promise<PromptPreviewResponse> {
  return requestJson<PromptPreviewResponse>(`${normalizeApiBaseUrl(apiBaseUrl)}/v1/prompt/demo`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ...buildProviderPayload(providerSettings),
      ...buildGoalPayload({ goalId, goalText, inferGoal }),
      scenario_id: scenarioId,
    }),
  });
}

export async function analyzeDemoFlow({
  apiBaseUrl,
  providerSettings,
  goalId,
  goalText,
  inferGoal,
  scenarioIds,
}: AnalyzeDemoFlowInput): Promise<FlowAnalysisResponse> {
  return requestJson<FlowAnalysisResponse>(`${normalizeApiBaseUrl(apiBaseUrl)}/v1/analyze/flow`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ...buildProviderPayload(providerSettings),
      ...buildGoalPayload({ goalId, goalText, inferGoal }),
      scenario_ids: scenarioIds,
    }),
  });
}

type GoalRequestInput = {
  goalId?: string;
  goalText?: string;
  inferGoal?: boolean;
};

function appendGoalFormData(formData: FormData, { goalId, goalText, inferGoal }: GoalRequestInput): void {
  const trimmedGoalText = goalText?.trim();
  if (trimmedGoalText) {
    formData.append("goal_text", trimmedGoalText);
  } else if (goalId) {
    formData.append("goal_id", goalId);
  }
  if (inferGoal) {
    formData.append("infer_goal", "true");
  }
}

function buildGoalPayload({ goalId, goalText, inferGoal }: GoalRequestInput) {
  const trimmedGoalText = goalText?.trim();
  return {
    ...(trimmedGoalText ? { goal_text: trimmedGoalText } : goalId ? { goal_id: goalId } : {}),
    ...(inferGoal ? { infer_goal: true } : {}),
  };
}

function appendProviderFormData(formData: FormData, providerSettings?: AiProviderSettings): void {
  const payload = buildProviderPayload(providerSettings);
  Object.entries(payload).forEach(([key, value]) => {
    formData.append(key, value);
  });
}

function buildProviderPayload(providerSettings?: AiProviderSettings) {
  if (!providerSettings || providerSettings.providerId === "server") {
    return {};
  }
  const payload: Record<string, string> = {
    provider_id: providerSettings.providerId,
  };
  if (providerSettings.apiKey.trim()) {
    payload.provider_api_key = providerSettings.apiKey.trim();
  }
  if (providerSettings.model.trim()) {
    payload.provider_model = providerSettings.model.trim();
  }
  if (providerSettings.baseUrl.trim()) {
    payload.provider_base_url = normalizeApiBaseUrl(providerSettings.baseUrl);
  }
  return payload;
}

export function normalizeApiBaseUrl(apiBaseUrl: string): string {
  const trimmed = apiBaseUrl.trim();
  if (!trimmed) {
    throw new ExitGuideApiError("API 주소를 먼저 입력하세요.");
  }

  const withProtocol = /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
  return withProtocol.replace(/\/+$/, "");
}

export async function fetchRuntimeApiBaseUrl(): Promise<string | null> {
  const runtimeConfigUrl = getRuntimeConfigUrl();
  if (!runtimeConfigUrl) {
    return null;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), RUNTIME_CONFIG_TIMEOUT_MS);
  try {
    // The revisionless GitHub Gist raw URL is intentionally stable, but its
    // CDN may briefly serve the previous tunnel address after an edit. A
    // per-launch cache buster keeps installed APKs from replacing a fresh
    // build fallback with an expired cached address.
    const separator = runtimeConfigUrl.includes("?") ? "&" : "?";
    const requestUrl = `${runtimeConfigUrl}${separator}exitguide_ts=${Date.now()}`;
    const response = await fetch(requestUrl, {
      headers: {
        Accept: "application/vnd.github.raw+json",
        "Cache-Control": "no-cache",
      },
      signal: controller.signal,
    });
    if (!response.ok) {
      return null;
    }

    const config = (await response.json()) as MobileRuntimeConfig;
    if (config.schema_version !== 1 || !config.active || typeof config.api_base_url !== "string") {
      return null;
    }

    const normalized = normalizeApiBaseUrl(config.api_base_url);
    return normalized.toLowerCase().startsWith("https://") ? normalized : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function getDefaultApiBaseUrl(): string {
  const hostUri = Constants.expoConfig?.hostUri ?? Constants.manifest2?.extra?.expoGo?.debuggerHost;
  const host = typeof hostUri === "string" ? hostUri.split(":")[0] : null;

  if (host && host !== "localhost" && host !== "127.0.0.1") {
    return `http://${host}:${API_PORT}`;
  }

  const configuredApiBaseUrl = Constants.expoConfig?.extra?.apiBaseUrl;
  if (typeof configuredApiBaseUrl === "string" && configuredApiBaseUrl.trim()) {
    return normalizeApiBaseUrl(configuredApiBaseUrl);
  }

  return `http://127.0.0.1:${API_PORT}`;
}

function getRuntimeConfigUrl(): string | null {
  const configuredUrl = Constants.expoConfig?.extra?.runtimeConfigUrl;
  if (typeof configuredUrl !== "string") {
    return null;
  }
  const trimmed = configuredUrl.trim();
  return trimmed.toLowerCase().startsWith("https://") ? trimmed : null;
}

async function requestJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      signal: controller.signal,
    });
  } catch (error) {
    const aborted = error instanceof Error && error.name === "AbortError";
    throw new ExitGuideApiError(
      aborted
        ? "API가 제시간에 응답하지 않았습니다. 서버 실행 여부와 휴대폰/노트북 네트워크를 확인하세요."
        : "ExitGuide API에 연결할 수 없습니다. API 주소와 네트워크 연결을 확인하세요.",
    );
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    const body = await safeReadBody(response);
    throw new ExitGuideApiError(body || `Request failed with HTTP ${response.status}.`, response.status);
  }

  return (await response.json()) as T;
}

async function safeReadBody(response: Response): Promise<string | null> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") {
      return body.detail;
    }
    return JSON.stringify(body);
  } catch {
    return null;
  }
}
