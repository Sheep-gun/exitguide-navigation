import type { Goal, GoalDefinition } from "../types";

const fallbackDescriptions: Record<string, string> = {
  protect_user_intent: "해지 방해, 추가 결제, 선택 동의, 탈퇴 방해를 한 번에 확인합니다.",
  cancel_subscription: "구독 해지가 실제로 진행되는 선택지를 확인합니다.",
  cancel_trial: "자동 결제 시점과 체험 해지 버튼이 숨어 있는지 확인합니다.",
  buy_without_addons: "결제 전 선택된 부가 상품과 추가 비용을 확인합니다.",
  reject_marketing: "필수 약관과 선택 마케팅 동의를 분리해 확인합니다.",
  delete_account: "탈퇴 진행 경로와 데이터 안내를 함께 확인합니다.",
};

export const fallbackGoals: Goal[] = [
  {
    id: "protect_user_intent",
    title: "원치 않는 유도 피하기",
    description: fallbackDescriptions.protect_user_intent,
  },
  {
    id: "cancel_subscription",
    title: "구독 해지하기",
    description: fallbackDescriptions.cancel_subscription,
  },
  {
    id: "cancel_trial",
    title: "무료 체험 해지하기",
    description: fallbackDescriptions.cancel_trial,
  },
  {
    id: "buy_without_addons",
    title: "추가 비용 없이 결제하기",
    description: fallbackDescriptions.buy_without_addons,
  },
  {
    id: "reject_marketing",
    title: "선택 마케팅 동의 거절하기",
    description: fallbackDescriptions.reject_marketing,
  },
  {
    id: "delete_account",
    title: "계정 탈퇴하기",
    description: fallbackDescriptions.delete_account,
  },
];

export function mapGoalDefinitions(definitions: GoalDefinition[]): Goal[] {
  return definitions.map((definition) => ({
    id: definition.id,
    title: definition.label,
    description:
      definition.description ??
      fallbackDescriptions[definition.id] ??
      "보이는 화면 선택지가 목표와 맞는지 확인합니다.",
  }));
}
