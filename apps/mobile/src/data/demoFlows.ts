import type { DemoFlow, DemoFlowDefinition } from "../types";

export const fallbackDemoFlows: DemoFlow[] = [
  {
    id: "subscription_cancel_path",
    title: "해지 흐름 점검",
    description: "유지 유도 화면과 최종 해지 확인 화면을 비교합니다.",
    goalId: "protect_user_intent",
    scenarioIds: ["subscription_cancel", "subscription_confirmation"],
  },
  {
    id: "trial_cancel_path",
    title: "체험 해지 흐름",
    description: "자동 결제 압박 화면과 해지 완료 화면을 비교합니다.",
    goalId: "protect_user_intent",
    scenarioIds: ["trial_renewal", "trial_success"],
  },
  {
    id: "addon_risk_contrast",
    title: "부가 비용 비교",
    description: "기본 선택된 부가 상품 결제와 깨끗한 결제를 비교합니다.",
    goalId: "protect_user_intent",
    scenarioIds: ["checkout_addons", "checkout_clean"],
  },
  {
    id: "account_delete_path",
    title: "탈퇴 흐름 점검",
    description: "계정 유지 유도 화면과 최종 탈퇴 확인 화면을 비교합니다.",
    goalId: "protect_user_intent",
    scenarioIds: ["account_deletion", "account_deletion_confirmation"],
  },
];

export function mapDemoFlowDefinitions(definitions: DemoFlowDefinition[]): DemoFlow[] {
  return definitions.map((definition) => ({
    id: definition.id,
    title: definition.label,
    description: definition.description,
    goalId: definition.goal_id,
    scenarioIds: definition.scenario_ids,
  }));
}
