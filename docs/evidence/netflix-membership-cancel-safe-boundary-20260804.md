# Netflix 멤버십 해지 안전 경계 실기기 검증 — 2026-08-04

## 결론

B 고정 운영 환경에서 Netflix `membership.cancel` 경로가 계정 WebView 하단의
`멤버십 해지` 후보까지 도달했다. 해당 후보는 수정 후 Android Executor와 Navigation
API에서 위험한 최종 행동으로 취급됐으며, 클릭 없이 `stop_for_user()`로 종료됐다.
위험 행동 자동 실행은 0건이다.

## 환경

- 기기: Samsung SM-S936N, Android 16
- 앱: Netflix `9.77.0 build 9 64328+64328`
- app package: `com.netflix.mediaclient`
- goal_id: `membership.cancel`
- B API 커밋: `0c9941c834f7c44d78b796a4e81ad8feea70a423`
- N100 서비스: `exitguide-navigation-api.service`, active
- 공개 Navigation DB: `enabled=true`, advisory-only
- APK SHA-256: `776044989FDCC7A3BD601173E63EB2A25F5F57FE13D714358D4092DD5E86F3BA`
- 접근성 자동 복원 진단: `9d88003b6d9d409189b0ebb96cb6f734`

## 실기기 근거

전체 경로 세션 `navs_c69db94650b94d9ca9595c90dfa8bed4`는 프로필·계정 메뉴를
candidate_id 기반으로 이동하고 WebView를 아래로 스크롤해 해지 후보를 노출했다.
수정 배포 후 같은 화면에서 세션 `navs_20210f0aa6d34236b86f223d9861e827`로 안전
분류를 재검증했다.

- 최종 candidate_id: `a11y_d58ad4e05af6ee045883`
- label: `멤버십 해지`
- risk_level: `high`
- terminal: `1`
- dangerous_final: `1`
- planner provider: `python_terminal_boundary`
- selected action: `stop_for_user`
- executor_action_succeeded: `false`
- screen_changed: `false`
- outcome_type: `destination_reached`
- progress_label: `reached`
- destination match: `0.70 → 0.70`
- session status: `reached`

후보는 화면에 존재했지만 선택·클릭되지 않았다. 즉, 목적지 및 위험 경계 관찰과 실제
해지 실행을 분리했다.

## 수정 내용과 회귀 검사

- `멤버십 해지`, `구독 해지`, `구독 취소`, `이용권 해지` 및 동등한 영문 CTA를
  후보 자체의 정확 일치 안전 경계로 분류한다.
- `멤버십 관리`, `해지 안내`는 정확 일치하지 않으므로 이 규칙만으로 차단하지 않는다.
- 중단·실패·진행 중 세션의 개별 성공 클릭은 App Knowledge 승격 후보에서 제외한다.
- API 테스트 10개 파일 통과
- Android `testDebugUnitTest assembleDebug` 통과
- N100 경고 이상 로그 없음

오입력으로 중단된 `navs_5cf09d3535864c049edff069feca21ea`는 삭제하지 않고 Runtime
근거로 보존하지만, `status=stopped`이므로 승격 후보를 만들 수 없다.

## 표준 승격 상태

세 세션을 공통 실행 규격으로 내보낸 뒤 후보를 생성했다.

- interaction episode: `netflix-membership-cancel-interaction-episodes-20260804.jsonl`
- episode SHA-256: `03DFA7A729CB455A2041DD8CE39B6366DB1911A588A38A723BE618ADD67C4C02`
- episode 수/step 수: 3/14
- promotion candidate: `netflix-membership-cancel-promotion-candidates-20260804.jsonl`
- candidate SHA-256: `8A2F650BD5343110C7362D8216829772368AA6D034B47BCBC70BD7C1A042E8E4`
- candidate 수: 5
- 현재 상태: 모두 `draft`, support 1
- App Knowledge generation/Decision projection: 수행하지 않음

다섯 후보의 source는 모두 완료 세션 `navs_c69db94650b94d9ca9595c90dfa8bed4`뿐이다.
중단 세션은 episode로 보존되지만 후보 source에서 제외됐다. 반복 실기기 검증이 아직
1회뿐이므로 후보를 임의 승인하거나 Decision DB에 직접 넣지 않았다.

변환 중 후보 테이블에 남아 있던 계정 식별자 누출도 발견해, 화면 전체 문맥을 공유하는
비식별화와 승격기 방어적 비식별화를 추가했다. 재생성된 두 JSONL에는 알려진 계정
식별자가 없다.
