import type { RiskLevel } from "../types";

export function riskLabel(risk: RiskLevel): string {
  if (risk === "high") {
    return "높음";
  }
  if (risk === "medium") {
    return "주의";
  }
  return "낮음";
}

export function modeLabel(mode: "demo" | "upload"): string {
  return mode === "demo" ? "데모" : "업로드";
}
