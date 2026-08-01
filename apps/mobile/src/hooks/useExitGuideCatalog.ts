import { useEffect, useState } from "react";

import {
  fetchApiStatus,
  fetchDemoQuality,
  fetchDemoFlows,
  fetchDemoScenarios,
  fetchGoals,
  fetchReadiness,
} from "../api/exitguideApi";
import {
  fallbackDemoScenarios,
  mapDemoScenarioDefinitions,
} from "../data/demoScenarios";
import { fallbackDemoFlows, mapDemoFlowDefinitions } from "../data/demoFlows";
import { fallbackGoals, mapGoalDefinitions } from "../data/goals";
import type { ApiStatus, DemoFlow, DemoQuality, DemoReadiness, DemoScenario, Goal } from "../types";

type CatalogSource = "api" | "fallback";

export function useExitGuideCatalog(apiBaseUrl: string) {
  const [apiStatus, setApiStatus] = useState<ApiStatus | null>(null);
  const [catalogMessage, setCatalogMessage] = useState<string | null>(null);
  const [catalogSource, setCatalogSource] = useState<CatalogSource>("fallback");
  const [demoQuality, setDemoQuality] = useState<DemoQuality | null>(null);
  const [demoReadiness, setDemoReadiness] = useState<DemoReadiness | null>(null);
  const [demoFlows, setDemoFlows] = useState<DemoFlow[]>(fallbackDemoFlows);
  const [demoScenarios, setDemoScenarios] = useState<DemoScenario[]>(fallbackDemoScenarios);
  const [goals, setGoals] = useState<Goal[]>(fallbackGoals);
  const [isCatalogLoading, setIsCatalogLoading] = useState(false);

  useEffect(() => {
    let mounted = true;

    async function loadCatalog() {
      if (!apiBaseUrl.trim()) {
        setIsCatalogLoading(false);
        setApiStatus(null);
        setDemoQuality(null);
        setDemoReadiness(null);
        setCatalogSource("fallback");
        setCatalogMessage("실시간 목표와 데모를 불러오려면 API 주소를 입력하세요.");
        setDemoFlows(fallbackDemoFlows);
        setDemoScenarios(fallbackDemoScenarios);
        setGoals(fallbackGoals);
        return;
      }

      setIsCatalogLoading(true);
      try {
        const [status, readiness, goalDefinitions, scenarioDefinitions, flowDefinitions] = await Promise.all([
          fetchApiStatus(apiBaseUrl),
          fetchReadiness(apiBaseUrl),
          fetchGoals(apiBaseUrl),
          fetchDemoScenarios(apiBaseUrl),
          fetchDemoFlows(apiBaseUrl),
        ]);

        if (!mounted) {
          return;
        }

        const nextGoals = mapGoalDefinitions(goalDefinitions);
        const nextScenarios = mapDemoScenarioDefinitions(scenarioDefinitions);
        const nextFlows = mapDemoFlowDefinitions(flowDefinitions);
        setApiStatus(status);
        setDemoQuality(null);
        setDemoReadiness(readiness);
        setGoals(nextGoals.length ? nextGoals : fallbackGoals);
        setDemoScenarios(nextScenarios.length ? nextScenarios : fallbackDemoScenarios);
        setDemoFlows(nextFlows.length ? nextFlows : fallbackDemoFlows);
        setCatalogSource("api");
        setCatalogMessage(null);
        void fetchDemoQuality(apiBaseUrl)
          .then((quality) => {
            if (mounted) {
              setDemoQuality(quality);
            }
          })
          .catch(() => {
            // Quality calibration is diagnostic metadata, not an API
            // connectivity prerequisite for the mobile experience.
          });
      } catch (error) {
        if (!mounted) {
          return;
        }

        const message = error instanceof Error ? error.message : "Using the built-in demo catalog.";
        setApiStatus(null);
        setDemoQuality(null);
        setDemoReadiness(null);
        setGoals(fallbackGoals);
        setDemoFlows(fallbackDemoFlows);
        setDemoScenarios(fallbackDemoScenarios);
        setCatalogSource("fallback");
        setCatalogMessage(message);
      } finally {
        if (mounted) {
          setIsCatalogLoading(false);
        }
      }
    }

    loadCatalog();

    return () => {
      mounted = false;
    };
  }, [apiBaseUrl]);

  return {
    apiStatus,
    catalogMessage,
    catalogSource,
    demoQuality,
    demoFlows,
    demoReadiness,
    demoScenarios,
    goals,
    isCatalogLoading,
  };
}
