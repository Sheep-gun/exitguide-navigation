import type { AiProviderId, AiProviderSettings } from "../types";

export const legacyGeminiFlashModel = "gemini-2.5-flash";
export const defaultGeminiFlashModel = "gemini-3-flash-preview";
export const defaultGeminiBaseUrl = "https://generativelanguage.googleapis.com/v1beta";

export const defaultProviderSettings: AiProviderSettings = {
  providerId: "server",
  apiKey: "",
  model: "",
  baseUrl: "",
};

export const providerDefaults: Record<AiProviderId, Pick<AiProviderSettings, "model" | "baseUrl">> = {
  server: {
    model: "",
    baseUrl: "",
  },
  google: {
    model: defaultGeminiFlashModel,
    baseUrl: defaultGeminiBaseUrl,
  },
  gpt: {
    model: "gpt-4.1-mini",
    baseUrl: "https://api.openai.com/v1",
  },
  exaone: {
    model: "LGAI-EXAONE/K-EXAONE-236B-A23B",
    baseUrl: "https://api.friendli.ai/serverless/v1",
  },
};

export const providerLabels: Record<AiProviderId, string> = {
  server: "서버",
  google: "Google",
  gpt: "GPT",
  exaone: "EXAONE",
};

export function withProviderDefaults(settings: AiProviderSettings): AiProviderSettings {
  const defaults = providerDefaults[settings.providerId];
  const model = normalizeProviderModel(settings.providerId, settings.model || defaults.model);
  return {
    providerId: settings.providerId,
    apiKey: settings.apiKey,
    model,
    baseUrl: normalizeProviderBaseUrl(settings.providerId, model, settings.baseUrl || defaults.baseUrl),
  };
}

function normalizeProviderModel(providerId: AiProviderId, model: string): string {
  if (providerId === "google" && model.trim() === legacyGeminiFlashModel) {
    return defaultGeminiFlashModel;
  }
  return model.trim();
}

function normalizeProviderBaseUrl(providerId: AiProviderId, model: string, baseUrl: string): string {
  const trimmed = baseUrl.trim().replace(/\/+$/, "");
  if (providerId === "google" && requiresGeminiBetaApi(model) && trimmed.endsWith("/v1")) {
    return `${trimmed.replace(/\/v1$/, "")}/v1beta`;
  }
  return trimmed;
}

function requiresGeminiBetaApi(model: string): boolean {
  const normalized = model.trim().toLowerCase();
  return normalized.startsWith("gemini-3-") || normalized.includes("preview");
}
