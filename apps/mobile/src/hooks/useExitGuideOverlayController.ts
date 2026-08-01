import { useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import {
  canDrawExitGuideOverlay,
  clearExitGuideOverlayStatus,
  isExitGuideAccessibilityEnabled,
  isExitGuideOverlayAvailable,
  openExitGuideAccessibilitySettings,
  openExitGuideOverlaySettings,
  startExitGuideOverlay,
  stopExitGuideOverlay,
} from "../native/ExitGuideOverlay";
import type { AiProviderSettings } from "../types";

export function useExitGuideOverlayController() {
  const [hasPermission, setHasPermission] = useState(false);
  const [hasAccessibility, setHasAccessibility] = useState(false);
  const [startBusy, setStartBusy] = useState(false);
  const [stopBusy, setStopBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const operationRef = useRef<"start" | "stop" | null>(null);

  function releaseOperation(operation?: "start" | "stop") {
    if (operation === undefined || operation === "start") {
      setStartBusy(false);
    }
    if (operation === undefined || operation === "stop") {
      setStopBusy(false);
    }
    if (operation === undefined || operationRef.current === operation) {
      operationRef.current = null;
    }
  }

  useEffect(() => {
    void refreshPermission();
    const subscription = AppState.addEventListener("change", (state) => {
      // A native command is already dispatched before ExitGuide can move to
      // the background. Do not keep controls locked while JS is suspended.
      releaseOperation();
      if (state !== "active") {
        return;
      }
      void refreshPermission();
    });
    return () => subscription.remove();
  }, []);

  async function refreshPermission() {
    const [overlayAllowed, accessibilityAllowed] = await Promise.all([
      canDrawExitGuideOverlay(),
      isExitGuideAccessibilityEnabled(),
    ]);
    setHasPermission(overlayAllowed);
    setHasAccessibility(accessibilityAllowed);
  }

  async function openOverlaySettings() {
    setMessage(null);
    await openExitGuideOverlaySettings();
  }

  async function openAccessibilitySettings() {
    setMessage(null);
    await openExitGuideAccessibilitySettings();
  }

  async function startNavigation(
    apiBaseUrl: string,
    purposeText: string,
    providerSettings: AiProviderSettings,
  ) {
    if (operationRef.current !== null) {
      return;
    }
    setMessage(null);
    try {
      if (!isExitGuideOverlayAvailable) {
        setMessage("Expo Go에서는 미리보기만 가능합니다. APK에서 화면 위 아이콘이 켜집니다.");
        return;
      }
      const [overlayAllowed, accessibilityAllowed] = await Promise.all([
        canDrawExitGuideOverlay(),
        isExitGuideAccessibilityEnabled(),
      ]);
      setHasPermission(overlayAllowed);
      setHasAccessibility(accessibilityAllowed);
      if (!overlayAllowed) {
        setMessage("Android 설정에서 화면 위 표시 권한을 켠 뒤 다시 누르세요.");
        void openExitGuideOverlaySettings();
        return;
      }
      if (!accessibilityAllowed) {
        setMessage("Android 접근성 설정에서 ExitGuide Navigation을 켠 뒤 다시 누르세요.");
        void openExitGuideAccessibilitySettings();
        return;
      }
      operationRef.current = "start";
      const command = startExitGuideOverlay(apiBaseUrl, purposeText.trim(), providerSettings);
      // The operation ref already prevents duplicate dispatches.  Do not turn
      // the button into a loading control: React Native state updates can be
      // suspended as soon as the target app opens, leaving a stale busy flag
      // when the user comes back to ExitGuide.
      releaseOperation("start");
      void command
        .then(() => {
          setMessage("탐색을 시작했습니다. 플로팅 아이콘을 누르면 언제든 ExitGuide로 돌아옵니다.");
        })
        .catch((error: unknown) => {
          setMessage(error instanceof Error ? error.message : "화면 위 아이콘을 켜지 못했습니다.");
        })
        .finally(() => releaseOperation("start"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "화면 위 아이콘을 켜지 못했습니다.");
    } finally {
      releaseOperation("start");
    }
  }

  async function stopNavigation() {
    if (operationRef.current !== null) {
      return;
    }
    operationRef.current = "stop";
    setMessage(null);
    try {
      const command = stopExitGuideOverlay();
      releaseOperation("stop");
      void command
        .then(() => {
          setMessage("화면 위 아이콘을 껐습니다.");
        })
        .catch((error: unknown) => {
          setMessage(error instanceof Error ? error.message : "화면 위 아이콘을 끄지 못했습니다.");
        })
        .finally(() => releaseOperation("stop"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "화면 위 아이콘을 끄지 못했습니다.");
    } finally {
      releaseOperation("stop");
    }
  }

  async function clearNavigation() {
    setMessage(null);
    try {
      await clearExitGuideOverlayStatus();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "이전 탐색 상태를 지우지 못했습니다.");
    }
  }

  return {
    clearNavigation,
    hasAccessibility,
    hasPermission,
    message,
    openAccessibilitySettings,
    openOverlaySettings,
    startBusy,
    startNavigation,
    stopBusy,
    stopNavigation,
  };
}
