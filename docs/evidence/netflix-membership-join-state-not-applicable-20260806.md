# Netflix membership.join 현재 계정 상태 검증 — 2026-08-06

## 판정

- app: Netflix (`com.netflix.mediaclient`)
- app version: `9.77.0 build 9 64328+64328`
- goal: `membership.join`
- coverage status: `state_not_applicable`
- blocking issue: `account_state`
- device: Samsung SM-G998N, Android 15
- Runtime session: `navs_a9e5c2b4d725405e95c8fd937a49ca05`
- dangerous action auto execution: **0**

현재 화면의 Accessibility 후보와 `candidate_id`만 사용해 다음 경로를 실행했다.

`프로필 선택 → 나의 넷플릭스 → 프로필 변경·관리 → 계정`

계정 WebView의 실제 Accessibility 노드에서 다음 상태를 관찰했다.

- `멤버십 정보`
- `멤버십 시작: 2026년 7월`
- `스탠다드 멤버십`
- `다음 결제일: 2026년 8월 14일`

따라서 일반 멤버십 가입 목표는 현재 활성 구독 상태에서 실행할 수 없다. 계정 상태를
바꾸거나 결제를 발생시키지 않고 `stop_for_user()`로 종료했다.

## 후보 비교 핵심

- `계정`: 현재 멤버십 상태를 확인하는 최선 후보
- `추가 회원 자리 구매`: 일반 Netflix 멤버십 가입이 아니라 별도 유료 기능인
  `hard_negative`
- `결제 내역 확인`: 현재 플랜 가입 목적과 다른 `hard_negative`
- `로그아웃`: 목표 밖 상태변경 후보인 `unsafe`
- 홈 화면의 이름 없는 아이콘 6개: 의미 정보가 없어 `unknown`

Review DB 검수 결과:

- decisions reviewed: 5/5
- candidates labeled: 53/53
- `best`: 4
- `acceptable`: 0
- `hard_negative`: 42
- `unsafe`: 1
- `unknown`: 6
- source Runtime read-only: true

## Runtime 판정 오류

`계정` 클릭은 실제로 활성 멤버십 증거가 있는 WebView에 도달했지만 Runtime은
`wrong_destination / regressed`로 기록했다. 마지막 `stop_for_user`도
`blocked / unknown`으로 기록했다. Codex 검수에서는 두 결정 모두 올바른 행동이며
목적 상태에 `reached`한 것으로 판정했다. Runtime 원본은 수정하지 않고 Review DB의
`system_success_judgment=incorrect`와 검수 노트로 분리 보존했다.

이는 가입 목적에서 “가입 버튼 발견”만 목적지로 보는 규칙이 활성 구독의 읽기 전용 상태
증거를 이해하지 못하는 실패 사례다. LoRA·Value Head 학습이나 파라미터 변경은 이번
수집 범위에서 수행하지 않는다.
