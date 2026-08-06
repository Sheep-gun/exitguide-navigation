# Netflix membership.change 실기기 근거

- session: `navs_70bba57439ed4f4e8d9f0c571f61abcc`
- app: `com.netflix.mediaclient`, `9.77.0 build 9 64328+64328`
- goal_id: `membership.change`
- result: `not_testable`
- blocking_issue: `service_policy`
- dangerous automatic action: 0

## 실제 관찰

현재 화면에서 발견된 candidate_id만 사용해 프로필 선택 → 나의 넷플릭스 → 프로필 관리
시트 → 계정 WebView로 이동했다. 계정 화면에서 `스탠다드 멤버십`, 멤버십 시작 시점과
다음 결제일을 확인한 뒤 90% 하향 스크롤로 계정 페이지를 끝까지 조사했다.

현재 계정 화면에는 `요금제 변경`, `플랜 변경`, `업그레이드`, `다운그레이드` 후보가
없었다. `추가 회원 자리 구매`는 별도 유료 기능, `멤버십 해지`는 반대 목적이므로 변경
성공으로 처리하지 않았다. 계정·구독 상태를 바꾸지 않고 `stop_for_user()`로 종료했다.

## Runtime과 Review

- Runtime decisions: 7
- candidate_id clicks: 4
- 90% scrolls: 2
- Review decisions: 7 / 7
- candidate labels: 81 / 81
- labels: best 4, acceptable 0, hard_negative 68, unsafe 3, unknown 6
- Review source: `codex-yanggeon`, `verified`
- Runtime source read-only: true

Runtime은 프로필 메뉴 진입을 `wrong_destination/regressed`, 계정 WebView 진입을
`progress unknown`, 마지막 종료를 `blocked`로 기록했다. 실제 전이는 목적 방향으로
올바랐고 마지막 상태는 탐색 차단이 아니라 현재 서비스·계정 구성에서 변경 후보가 없는
`not_testable`이다. 이 교정은 별도 Review DB에만 저장했으며 Runtime 원본은 수정하지
않았다.

초기 operator 명령 한 건은 허용되지 않은 reason code 때문에 API 422로 거절됐다. 클릭은
실행되지 않았고 Runtime decision도 생성되지 않았으므로 연결·계약 오류로만 취급한다.
