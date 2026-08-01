import type { DemoScenario, DemoScenarioDefinition } from "../types";

export const fallbackDemoScenarios: DemoScenario[] = [
  {
    id: "subscription_cancel",
    title: "구독 해지 방해",
    description: "해지 진행 버튼보다 유지 혜택을 더 강하게 보여주는 화면입니다.",
    recommendedGoalId: "protect_user_intent",
    fixtureFilename: "subscription-cancel-retention.png",
  },
  {
    id: "subscription_confirmation",
    title: "구독 해지 완료 확인",
    description: "다음 결제 없음이 명확하게 보이는 낮은 위험 화면입니다.",
    recommendedGoalId: "protect_user_intent",
    fixtureFilename: "subscription-cancel-confirmation.png",
  },
  {
    id: "trial_renewal",
    title: "무료 체험 자동 결제",
    description: "곧 결제될 금액과 체험 연장 유도가 함께 있는 화면입니다.",
    recommendedGoalId: "protect_user_intent",
    fixtureFilename: "trial-renewal-warning.png",
  },
  {
    id: "trial_success",
    title: "무료 체험 해지 완료",
    description: "체험 해지와 다음 결제 없음이 확인되는 낮은 위험 화면입니다.",
    recommendedGoalId: "protect_user_intent",
    fixtureFilename: "trial-cancel-success.png",
  },
  {
    id: "checkout_addons",
    title: "결제 부가 상품",
    description: "선택 부가 상품이 기본 선택된 결제 화면입니다.",
    recommendedGoalId: "protect_user_intent",
    fixtureFilename: "checkout-preselected-addon.png",
  },
  {
    id: "checkout_clean",
    title: "깨끗한 결제",
    description: "선택 부가 상품이 보이지만 기본 선택되지 않은 낮은 위험 화면입니다.",
    recommendedGoalId: "protect_user_intent",
    fixtureFilename: "checkout-no-preselected-addon.png",
  },
  {
    id: "marketing_consent",
    title: "마케팅 동의 묶음",
    description: "전체 동의에 선택 마케팅 동의가 섞여 있는 화면입니다.",
    recommendedGoalId: "protect_user_intent",
    fixtureFilename: "marketing-consent-optional.png",
  },
  {
    id: "required_terms_only",
    title: "필수 약관만 있는 화면",
    description: "선택 마케팅 동의 없이 필수 약관만 확인되는 낮은 위험 화면입니다.",
    recommendedGoalId: "protect_user_intent",
    fixtureFilename: "consent-required-only.png",
  },
  {
    id: "account_deletion",
    title: "계정 탈퇴 방해",
    description: "탈퇴 진행보다 계정 유지 버튼을 더 강하게 보여주는 화면입니다.",
    recommendedGoalId: "protect_user_intent",
    fixtureFilename: "account-delete-retention.png",
  },
  {
    id: "account_deletion_confirmation",
    title: "계정 탈퇴 완료 확인",
    description: "탈퇴 완료와 데이터 안내가 명확한 낮은 위험 화면입니다.",
    recommendedGoalId: "protect_user_intent",
    fixtureFilename: "account-delete-confirmation.png",
  },
];

export function mapDemoScenarioDefinitions(definitions: DemoScenarioDefinition[]): DemoScenario[] {
  return definitions.map((definition) => ({
    id: definition.id,
    title: definition.label,
    description: definition.description,
    recommendedGoalId: definition.recommended_goal_id,
    fixtureFilename: definition.fixture_filename,
  }));
}
