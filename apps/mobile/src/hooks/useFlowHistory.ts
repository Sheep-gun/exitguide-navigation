import { useCallback, useEffect, useState } from "react";

import {
  clearFlowHistory,
  limitFlowHistory,
  loadFlowHistory,
  saveFlowHistory,
} from "../storage/flowHistoryStore";
import type { FlowAnalysisResponse, FlowHistoryItem } from "../types";

export function useFlowHistory() {
  const [flowHistory, setFlowHistory] = useState<FlowHistoryItem[]>([]);
  const [isFlowHistoryLoaded, setIsFlowHistoryLoaded] = useState(false);

  useEffect(() => {
    let mounted = true;

    loadFlowHistory()
      .then((items) => {
        if (mounted) {
          setFlowHistory(items);
        }
      })
      .finally(() => {
        if (mounted) {
          setIsFlowHistoryLoaded(true);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (isFlowHistoryLoaded) {
      saveFlowHistory(flowHistory).catch(() => undefined);
    }
  }, [flowHistory, isFlowHistoryLoaded]);

  const addFlowHistoryItem = useCallback((flow: FlowAnalysisResponse, sourceLabel: string | null) => {
    const nextItem = createFlowHistoryItem(flow, sourceLabel);
    const nextKey = flowHistoryKey(flow);
    setFlowHistory((items) =>
      limitFlowHistory([
        nextItem,
        ...items.filter((item) => flowHistoryKey(item.flow) !== nextKey),
      ]),
    );
  }, []);

  const clearFlows = useCallback(() => {
    setFlowHistory([]);
    clearFlowHistory().catch(() => undefined);
  }, []);

  return {
    addFlowHistoryItem,
    clearFlows,
    flowHistory,
  };
}

function createFlowHistoryItem(flow: FlowAnalysisResponse, sourceLabel: string | null): FlowHistoryItem {
  return {
    id: flow.flow_id ?? `${Date.now()}-${flow.goal_id}-${flow.screens.length}`,
    createdAt: formatClock(new Date()),
    flow,
    sourceLabel,
  };
}

function flowHistoryKey(flow: FlowAnalysisResponse): string {
  return flow.flow_id ?? `${flow.goal_id}-${flow.screens.map((screen) => screen.screen_title).join("/")}`;
}

function formatClock(date: Date): string {
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
}
