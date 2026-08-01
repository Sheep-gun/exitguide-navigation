import { useEffect, useState } from "react";

import { DEFAULT_API_BASE_URL, fetchRuntimeApiBaseUrl, normalizeApiBaseUrl } from "../api/exitguideApi";
import { loadApiBaseUrl, saveApiBaseUrl } from "../storage/apiSettingsStore";

export function useStoredApiBaseUrl() {
  const [apiBaseUrl, setApiBaseUrl] = useState(DEFAULT_API_BASE_URL);
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    let mounted = true;

    async function loadApiConfiguration() {
      const storedApiBaseUrl = await loadApiBaseUrl().catch(() => null);
      if (mounted && storedApiBaseUrl) {
        setApiBaseUrl(storedApiBaseUrl);
      }

      // The published runtime URL must win over a previously persisted quick-tunnel
      // URL. Loading both values concurrently made this order nondeterministic and
      // could restore an expired host after the fresh runtime config had arrived.
      const runtimeApiBaseUrl = await fetchRuntimeApiBaseUrl();
      if (mounted && runtimeApiBaseUrl) {
        setApiBaseUrl(runtimeApiBaseUrl);
      }
      if (mounted) {
        setIsLoaded(true);
      }
    }

    void loadApiConfiguration();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (isLoaded && apiBaseUrl.trim()) {
      saveApiBaseUrl(normalizeApiBaseUrl(apiBaseUrl)).catch(() => undefined);
    }
  }, [apiBaseUrl, isLoaded]);

  return {
    apiBaseUrl,
    isLoaded,
    setApiBaseUrl,
  };
}
