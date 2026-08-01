import AsyncStorage from "@react-native-async-storage/async-storage";

import type { FlowHistoryItem } from "../types";

const FLOW_HISTORY_KEY = "exitguide.flowHistory.v1";
const MAX_FLOW_HISTORY_ITEMS = 5;

export async function loadFlowHistory(): Promise<FlowHistoryItem[]> {
  const raw = await AsyncStorage.getItem(FLOW_HISTORY_KEY);
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(isFlowHistoryItem).slice(0, MAX_FLOW_HISTORY_ITEMS);
  } catch {
    return [];
  }
}

export async function saveFlowHistory(items: FlowHistoryItem[]): Promise<void> {
  await AsyncStorage.setItem(FLOW_HISTORY_KEY, JSON.stringify(items.slice(0, MAX_FLOW_HISTORY_ITEMS)));
}

export async function clearFlowHistory(): Promise<void> {
  await AsyncStorage.removeItem(FLOW_HISTORY_KEY);
}

export function limitFlowHistory(items: FlowHistoryItem[]): FlowHistoryItem[] {
  return items.slice(0, MAX_FLOW_HISTORY_ITEMS);
}

function isFlowHistoryItem(value: unknown): value is FlowHistoryItem {
  if (!value || typeof value !== "object") {
    return false;
  }

  const item = value as Partial<FlowHistoryItem>;
  return Boolean(
    typeof item.id === "string" &&
      typeof item.createdAt === "string" &&
      item.flow &&
      typeof item.flow === "object" &&
      typeof item.flow.goal_id === "string" &&
      typeof item.flow.alignment_score === "number" &&
      typeof item.flow.screen_count === "number" &&
      (typeof item.flow.highest_risk_screen_number === "number" || item.flow.highest_risk_screen_number === null) &&
      Boolean(item.flow.risk_counts),
  );
}
