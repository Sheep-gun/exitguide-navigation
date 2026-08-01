import { useCallback, useEffect, useState } from "react";

import {
  clearAnalysisHistory,
  limitAnalysisHistory,
  loadAnalysisHistory,
  saveAnalysisHistory,
} from "../storage/analysisHistoryStore";
import type { AnalysisHistoryItem, AnalysisResponse } from "../types";

export function useAnalysisHistory() {
  const [history, setHistory] = useState<AnalysisHistoryItem[]>([]);
  const [isHistoryLoaded, setIsHistoryLoaded] = useState(false);

  useEffect(() => {
    let mounted = true;

    loadAnalysisHistory()
      .then((items) => {
        if (mounted) {
          setHistory(items);
        }
      })
      .finally(() => {
        if (mounted) {
          setIsHistoryLoaded(true);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (isHistoryLoaded) {
      saveAnalysisHistory(history).catch(() => undefined);
    }
  }, [history, isHistoryLoaded]);

  const addHistoryItem = useCallback((analysis: AnalysisResponse, sourceLabel: string | null) => {
    const nextItem = createHistoryItem(analysis, sourceLabel);
    const nextKey = analysisHistoryKey(analysis);
    setHistory((items) =>
      limitAnalysisHistory([
        nextItem,
        ...items.filter((item) => analysisHistoryKey(item.analysis) !== nextKey),
      ]),
    );
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
    clearAnalysisHistory().catch(() => undefined);
  }, []);

  return {
    addHistoryItem,
    clearHistory,
    history,
    isHistoryLoaded,
  };
}

function createHistoryItem(analysis: AnalysisResponse, sourceLabel: string | null): AnalysisHistoryItem {
  return {
    id: analysis.analysis_id ?? `${Date.now()}-${analysis.goal_id}-${analysis.screen_title}`,
    analysis,
    createdAt: formatClock(new Date()),
    sourceLabel,
  };
}

function analysisHistoryKey(analysis: AnalysisResponse): string {
  return analysis.analysis_id ?? `${analysis.goal_id}-${analysis.screen_title}-${analysis.analysis_mode}`;
}

function formatClock(date: Date): string {
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
}
