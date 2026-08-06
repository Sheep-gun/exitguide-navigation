# 쿠팡 멤버십 변경 현재 비구독 상태 — 2026-08-06

## 판정

- 앱: 쿠팡 `com.coupang.mobile` `9.3.5+2409350`
- 목표: `membership.change`
- 결과: `state_not_applicable`
- 차단 조건: `account_state`
- Runtime session: `navs_6a0d6c99439a44ed857c27887e9ef7e8`
- Runtime 원본 수정: 없음
- 위험 행동 자동 실행: 0건

## 실기기 관찰

쿠팡 홈의 `마이쿠팡` 후보 `a11y_75fdf13a7441a7a9ccce`를 Accessibility action으로
실행했고 실제 화면 변화를 관찰했다. 마이쿠팡 화면에는 다음 신규 가입 표현만 존재했다.

- `와우 1개월 무료 혜택 드려요`
- `와우 1개월 무료 혜택 드려요 지금받기`
- `와우 가입 즉시 드려요! 멤버십 1개월 무료 … 혜택받기`

활성 멤버십의 이용 중·관리·요금제 변경·상품 변경 후보는 없었다. 따라서 현재 계정은 와우
비구독 상태이며, 멤버십 변경은 적용되지 않는다. 가입 CTA나 결제 경로를 실행하지 않고
`stop_for_user()`로 종료했다.

## Review 골든 라벨

| decision_id | 행동 | 전체 후보 | 라벨 분포 |
|---|---|---:|---|
| `navd_cd2cc246eec2463788cfb2da9a76c83a` | `마이쿠팡` 클릭 | 25 | best 1, hard_negative 21, unknown 3 |
| `navd_2c72de0d88d14f8480c4fe259e73a560` | 상태 확인 후 중단 | 40 | hard_negative 23, unknown 17 |

합계 2개 결정과 65개 전체 후보를 reviewer `codex-yanggeon`, `label_source=codex`,
`review_status=verified`로 저장했다. 신규 가입 CTA는 변경 목표의 hard negative다. Runtime의
마지막 `blocked/unknown` 판정은 Human Review에서 현재 상태 목표 완료로 교정하되 원본은
수정하지 않았다.

수집기·Executor는 후보 수집, candidate_id 클릭, 화면 변화 관찰과 기록을 정상 수행했으므로
코드를 변경하지 않았다.
