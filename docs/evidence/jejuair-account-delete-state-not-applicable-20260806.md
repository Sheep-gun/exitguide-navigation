# 제주항공 account.delete 현재 계정 상태 실기기 근거

검증 일시: 2026-08-06 16:52–16:53 KST

## 판정

- goal_id: `account.delete`
- app: 제주항공 `com.parksmt.jejuair.android16` 5.9.8+781
- device: Samsung SM-G998N, Android 15
- Runtime session: `navs_3049480aa7cb4ced9617b2f41393e7d8`
- 결과: `state_not_applicable`
- blocking_issue: `account_state`

`account.signup`과 분리된 새 세션에서 홈의 `마이페이지`
(`a11y_b12cd340ce32209fd967`)를 현재 화면 candidate_id로 실행했다. 행동 후 제주항공
로그인 화면이 나타났고 Runtime은 `login_required / observed_login_required`를 기록한 뒤
세션을 안전 중단했다. 현재 계정은 로그아웃 상태라 삭제할 로그인 계정이 없다.

로그인 정보 입력이나 계정 상태 변경은 수행하지 않았다.

## Runtime과 Review

- decisions: 1
- complete before/after transitions: 1 / 1
- candidate-ID clicks: 1 / 1 grounded and executed
- Review decisions: 1 / 1
- before-screen candidates: 26
- verified candidate labels: 26 / 26
- labels: best 1, hard_negative 19, unknown 6
- source_read_only: true

`마이페이지`는 계정 상태를 확인하는 `best`, 홈의 비계정 기능은 `hard_negative`, 의미가
노출되지 않은 아이콘과 버튼은 `unknown`으로 검수했다. Runtime의 `login_required`는 현재
상태 판정 근거로 올바르므로 시스템 결과도 `correct`로 검수했다.

## 안전성

- 로그인 정보 입력: 0건
- 계정 상태 변경: 0건
- 위험 행동 자동 실행: 0건
- 연결 오류: 0건
