import AsyncStorage from "@react-native-async-storage/async-storage";

import type { AnalysisHistoryItem } from "../types";

const HISTORY_KEY = "exitguide.analysisHistory.v1";
const MAX_HISTORY_ITEMS = 8;

export async function loadAnalysisHistory(): Promise<AnalysisHistoryItem[]> {
  const raw = await AsyncStorage.getItem(HISTORY_KEY);
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(isHistoryItem).slice(0, MAX_HISTORY_ITEMS);
  } catch {
    return [];
  }
}

export async function saveAnalysisHistory(items: AnalysisHistoryItem[]): Promise<void> {
  await AsyncStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, MAX_HISTORY_ITEMS)));
}

export async function clearAnalysisHistory(): Promise<void> {
  await AsyncStorage.removeItem(HISTORY_KEY);
}

export function limitAnalysisHistory(items: AnalysisHistoryItem[]): AnalysisHistoryItem[] {
  return items.slice(0, MAX_HISTORY_ITEMS);
}

function isHistoryItem(value: unknown): value is AnalysisHistoryItem {
  if (!value || typeof value !== "object") {
    return false;
  }

  const item = value as Partial<AnalysisHistoryItem>;
  return Boolean(
    typeof item.id === "string" &&
      typeof item.createdAt === "string" &&
      item.analysis &&
      typeof item.analysis === "object" &&
      typeof item.analysis.goal_id === "string" &&
      typeof item.analysis.alignment_score === "number" &&
      Boolean(item.analysis.risk_counts),
  );
}
