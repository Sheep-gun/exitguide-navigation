import { useEffect, useState } from "react";

import { defaultProviderSettings, withProviderDefaults } from "../data/providers";
import { loadProviderSettings, saveProviderSettings } from "../storage/providerSettingsStore";
import type { AiProviderSettings } from "../types";

export function useStoredProviderSettings() {
  const [providerSettings, setProviderSettingsState] = useState<AiProviderSettings>(defaultProviderSettings);
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    let mounted = true;

    loadProviderSettings()
      .then((storedSettings) => {
        if (mounted) {
          setProviderSettingsState(storedSettings);
        }
      })
      .finally(() => {
        if (mounted) {
          setIsLoaded(true);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (isLoaded) {
      saveProviderSettings(providerSettings).catch(() => undefined);
    }
  }, [providerSettings, isLoaded]);

  function setProviderSettings(nextSettings: AiProviderSettings) {
    setProviderSettingsState(withProviderDefaults(nextSettings));
  }

  return {
    providerSettings,
    setProviderSettings,
  };
}
