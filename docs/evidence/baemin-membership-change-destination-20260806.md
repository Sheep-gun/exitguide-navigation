# 배달의민족 membership.change 실기기 근거

- session: `navs_9a549fb601764406811ad5f9f7f7ab8e`
- app: `com.sampleapp`, `16.16.0+26001143`
- goal_id: `membership.change`
- result: `destination_reached`
- dangerous automatic action: 0

현재 화면에서 수집된 candidate_id만 사용해 홈 → 마이배민 → 배민클럽 혜택 카드 →
마이배민클럽 → `배민클럽 이용 중 변경`으로 이동했다. 도착한 `배민클럽 관리` 화면에는
현재 이용 상품과 배민클럽 12개월·TVING·YouTube Premium 변경 상품이 표시됐다.
유료 상품 선택은 구독 변경으로 이어질 수 있어 실행하지 않고 `stop_for_user()`로 종료했다.

## 실패·복구 비교 사례

마이배민 상단의 배민클럽 혜택 카드는 쿠폰팩 문구로 노출돼 역할이 불명확했다. 첫 판단은
하단에 멤버십 메뉴가 있을 것으로 보고 90% 아래로 스크롤했지만 목적 후보에서 멀어졌다.
90% 위로 스크롤해 같은 화면으로 복구한 뒤 해당 카드를 클릭했고 마이배민클럽으로 실제
전환됐다.

Review DB에는 첫 하향 스크롤을 `wrong/regressed`, 같은 화면의 배민클럽 혜택 카드를
`best`, 상향 스크롤을 올바른 복구로 기록했다. 이는 동일 화면에서 잘못된 탐색 행동과
올바른 후보를 직접 비교할 수 있는 학습 사례다.

## Runtime과 Review

- Runtime decisions: 6
- evidence-complete decisions: 6 / 6
- candidate_id clicks: 3
- 90% scrolls: 2 (잘못된 하향 탐색 1, 성공한 상향 복구 1)
- Review decisions: 6 / 6
- candidate labels: 120 / 120
- labels: best 4, acceptable 3, hard_negative 102, unsafe 3, unknown 8
- wrong actions: 1
- paid product selections: 0
- Review source: `codex-yanggeon`, `verified`
- Runtime source read-only: true

Runtime은 모든 중간 진행을 `unknown`, 마지막 안전 종료를 `blocked`로 기록했다. Review
DB에서 실제 전진·목적지 도달·안전 handoff로 교정했으며 Runtime 원본은 수정하지 않았다.
