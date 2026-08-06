# 9개 파일럿 골든 라벨 게이트 감사 — 2026-08-06

## 결론

YouTube·Netflix·배달의민족의 `account.delete`, `membership.join`,
`membership.cancel` 9개 셀은 모두 실기기 근거가 있는 최종 상태다. 파일럿에 채택한
17개 Runtime 세션의 69개 의사결정과 1,082개 화면 후보를 전수 감사했다.

- Human Review: 69 / 69
- 후보 라벨: 1,082 / 1,082
- 분포: `best` 36, `acceptable` 13, `hard_negative` 986, `unsafe` 19,
  `unknown` 28
- 후보가 0개인 앱 시작 `wait_and_observe`: 1건, 행동 Review만 존재
- 실제 `click(candidate_id)`: 33건
- 클릭 ID가 현재 화면 후보 집합에 존재: 33 / 33
- Executor 클릭 성공: 33 / 33
- 고위험 후보 자동 클릭: 0건
- Runtime source: read-only

Review API 전역 수치는 감사 종료 시점에 1,278개 Runtime 결정 중 133개 검수,
1,145개 미검수였다. 나머지는 파일럿 채택 세션 밖의 기존 Runtime 원료이며 파일럿
게이트 통과 근거로 사용하지 않았다.

## 12개 통과 조건

| # | 조건 | 판정 | 근거 |
|---:|---|---|---|
| 1 | Accessibility 전체 후보 수집 | passed | 채택 결정의 before-screen 후보 집합이 모두 `complete`; 후보 1,082개 |
| 2 | candidate_id 생성 | passed | 후보 1,082개 모두 ID 보유 |
| 3 | 텍스트·아이콘·위치·주변 문구 | passed | 1,082개 모두 해당 필드가 직렬화됨 |
| 4 | 부모·자식 관계 | passed | 1,082개 모두 `parent_semantics`, `child_semantics` 필드 보유 |
| 5 | candidate_id 기반 실제 클릭 | passed | 33개 클릭 ID 전부 before-screen 집합에 존재하고 실행 성공 |
| 6 | 행동 전후 화면 기록 | passed | 유효 행동 68건은 before/after 보유; 아래 격리 1건은 전이 학습에서 제외하고 동일 경로를 재검증 |
| 7 | 화면 변화와 탐색 진행 분리 | passed | 유효 행동은 `state_changed`, `outcome_type`, `progress_label`을 별도 기록 |
| 8 | 선택 근거와 종료 이유 | passed | 모든 결정에 planner provider와 Human Review 노트가 있고 안전 경계는 `safe_user_handoff`로 종료 |
| 9 | Runtime DB와 Review DB 분리 | passed | Review 상세 응답 `source_read_only=true`; Runtime 원본 미수정 |
| 10 | 연결 오류와 탐색 실패 분리 | passed | 아래 422 관찰 실패를 연결/계약 오류로 보존하고 목적 미도달로 사용하지 않음 |
| 11 | 위험 행동 자동 실행 0건 | passed | 탈퇴·해지·결제·구독 확정 클릭 0건 |
| 12 | 데이터 분할 정책 | passed | 사용자 최신 지시에 따라 현재 11개 앱 모두 collection; 향후 새 미관측 앱만 validation·holdout |

## 격리된 불완전 전이

`navd_18e32b01411641d88471649fb705f912`는 배달의민족 회원탈퇴 화면에서 물리적 90%
스크롤은 실행됐지만 행동 후 `/observe`가 스키마 422로 거부돼 after snapshot과 결과 필드가
없다. 다음과 같이 처리했다.

1. Runtime 원본을 그대로 보존했다.
2. 연결·계약 오류를 탐색 실패로 바꾸지 않았다.
3. 해당 행을 성공 Transition 학습 근거에서 제외한다.
4. 수정 후 `navs_22145b3e172e4964a7129ef4b03c5189`에서 동일 경로의 후보 수집,
   실행, 화면 변화와 안전 경계를 다시 검증했다.

따라서 이 한 행은 실패 증거로 보존되지만 파일럿 통과를 주장하는 유효 전이 집합에는
포함하지 않는다.

## 파일럿 셀 결과

| 앱 | account.delete | membership.join | membership.cancel |
|---|---|---|---|
| YouTube | `destination_reached` | `state_not_applicable` | `safe_boundary_reached` |
| Netflix | `safe_boundary_reached` | `state_not_applicable` | `safe_boundary_reached` |
| 배달의민족 | `safe_boundary_reached` | `state_not_applicable` | `safe_boundary_reached` |

파일럿 게이트는 통과했다. 다만 현재 11개 앱을 모두 collection으로 바꾼 split과 최신
안전 경계 코드를 운영 8100에 배포하고 상태를 확인하기 전까지 대량 수집은 계속
일시정지한다.
