# NH농협손해보험 멤버십 변경 현재 계정 상태 근거

- 검증 시각: 2026-08-06 19:23~19:27 KST
- 기기: Samsung SM-G998N, Android 15
- 앱: NH농협손해보험 `ni.mh.android.launcher`, `1.434+476`
- goal_id: `membership.change`
- Runtime sessions: `navs_e032f988fa104436a8fd00f5234762f3`,
  `navs_b72ed298a3dc4abf9a57272ece178313`

## 관찰 결과

첫 세션에서는 팝업을 닫고 전체 메뉴를 열었다. 메뉴에는 NH포인트, 혜택/서비스,
마이페이지, 보험계약 `계약조회/변경`, `해지/환급`과 `로그인`이 함께 표시됐다. 메뉴가
실제로 열리고 63개 후보가 수집됐지만 API는 단순히 `로그인` 항목이 보인다는 이유로
`login_required`를 반환해 세션을 조기 종료했다. Review에서는 행동을 `acceptable`,
진행을 `advanced`, 시스템 성공 판정을 `incorrect`로 교정했다.

두 번째 세션에서는 홈의 `NH멤버스` 직접 후보를 실행했다. 개인고객 로그인·지문/Face ID·
인증수단 신규 등록 화면이 실제 관찰됐다. 현재 로그아웃 상태에서는 기존 멤버십 플랜이나
변경 기능을 확인할 수 없으므로 `state_not_applicable`, `blocking_issue=account_state`로
판정했다. 인증이나 상태 변경은 실행하지 않았다.

## Review 골든 라벨

- 결정: 4 / 4 검수
- 전체 후보: 161 / 161 검수
- 직접 NH멤버스 진입은 best, 부모 wrapper와 전체 메뉴는 acceptable로 구분했다.
- 보험상품 가입·계약조회·보험료 납입 등은 멤버십 변경과 다른 hard negative다.
- 메뉴의 보험계약 `해지/환급`은 멤버십 기능이 아니며 전이 화면 근거로 보존했다.

후보 수집·candidate_id 클릭·행동 전후 화면 기록은 정상이다. 이 사례는 수집기 실패가
아니라 API의 조기 로그인 요구 판정 오류다. Runtime 원본은 수정하지 않았고 위험 행동
자동 실행은 0건이다.
