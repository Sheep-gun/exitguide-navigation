import AsyncStorage from "@react-native-async-storage/async-storage";

import { defaultProviderSettings, withProviderDefaults } from "../data/providers";
import type { AiProviderId, AiProviderSettings } from "../types";

const PROVIDER_SETTINGS_KEY = "exitguide.providerSettings.v1";
const providerIds = new Set<AiProviderId>(["server", "google", "gpt", "exaone"]);

export async function loadProviderSettings(): Promise<AiProviderSettings> {
  const value = await AsyncStorage.getItem(PROVIDER_SETTINGS_KEY);
  if (!value) {
    return defaultProviderSettings;
  }

  try {
    const parsed = JSON.parse(value) as Partial<AiProviderSettings>;
    const providerId = providerIds.has(parsed.providerId as AiProviderId)
      ? (parsed.providerId as AiProviderId)
      : defaultProviderSettings.providerId;
    return withProviderDefaults({
      providerId,
      apiKey: parsed.apiKey ?? "",
      model: parsed.model ?? "",
      baseUrl: parsed.baseUrl ?? "",
    });
  } catch {
    return defaultProviderSettings;
  }
}

export async function saveProviderSettings(settings: AiProviderSettings): Promise<void> {
  await AsyncStorage.setItem(PROVIDER_SETTINGS_KEY, JSON.stringify(withProviderDefaults(settings)));
}
