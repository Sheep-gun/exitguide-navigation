import { Linking, NativeModules, Platform } from "react-native";

import type { AiProviderSettings } from "../types";

type ExitGuideOverlayModule = {
  canDrawOverlays: () => Promise<boolean>;
  openOverlaySettings: () => Promise<boolean>;
  isAccessibilityEnabled: () => Promise<boolean>;
  openAccessibilitySettings: () => Promise<boolean>;
  startOverlay: (
    apiBaseUrl: string,
    goalText: string,
    operationMode: "explore" | "record",
    providerId: string,
    providerApiKey: string,
    providerModel: string,
    providerBaseUrl: string,
  ) => Promise<string>;
  stopOverlay: () => Promise<boolean>;
  clearOverlayStatus: () => Promise<boolean>;
};

const nativeOverlay = NativeModules.ExitGuideOverlay as ExitGuideOverlayModule | undefined;

export const isExitGuideOverlayAvailable = Platform.OS === "android" && Boolean(nativeOverlay);

export async function canDrawExitGuideOverlay(): Promise<boolean> {
  if (!nativeOverlay) {
    return false;
  }
  return nativeOverlay.canDrawOverlays();
}

export async function openExitGuideOverlaySettings(): Promise<void> {
  if (!nativeOverlay) {
    await Linking.openSettings();
    return;
  }
  await nativeOverlay.openOverlaySettings();
}

export async function isExitGuideAccessibilityEnabled(): Promise<boolean> {
  if (!nativeOverlay) {
    return false;
  }
  return nativeOverlay.isAccessibilityEnabled();
}

export async function openExitGuideAccessibilitySettings(): Promise<void> {
  if (!nativeOverlay) {
    await Linking.openSettings();
    return;
  }
  await nativeOverlay.openAccessibilitySettings();
}

export async function startExitGuideOverlay(
  apiBaseUrl: string,
  goalText: string,
  providerSettings: AiProviderSettings,
  operationMode: "explore" | "record" = "explore",
): Promise<string> {
  if (!nativeOverlay) {
    throw new Error("화면 위 아이콘은 APK에서 사용할 수 있습니다.");
  }
  return nativeOverlay.startOverlay(
    apiBaseUrl,
    goalText,
    operationMode,
    providerSettings.providerId,
    providerSettings.apiKey,
    providerSettings.model,
    providerSettings.baseUrl,
  );
}

export async function stopExitGuideOverlay(): Promise<void> {
  if (!nativeOverlay) {
    return;
  }
  await nativeOverlay.stopOverlay();
}

export async function clearExitGuideOverlayStatus(): Promise<void> {
  if (!nativeOverlay) {
    return;
  }
  await nativeOverlay.clearOverlayStatus();
}
