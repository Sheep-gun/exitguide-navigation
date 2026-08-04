# Android Executor 90% 스크롤과 ADB 단절 자동 일시중지

## 발견한 문제

Netflix `membership.join` B 세션에서 기존 Executor의 스크롤은
`AccessibilityNodeInfo.ACTION_SCROLL_FORWARD`를 그대로 호출했다. 이 API는 실제 이동량을
앱에 맡기므로 화면 높이의 90% 이동을 보장하지 않는다.

- 첫 진단 세션: `navs_4e35dab60e3d4d5eb14ff2242a3bde36`
- 재실행 세션: `navs_f1367c3dd19a441a9c4c6288dc9fce23`
- B 공개 Prior: 활성화
- 실제 경로: Netflix 홈 → 나의 넷플릭스 → 프로필 관리 → 계정 WebView
- 기존 작은 스크롤: 4회 연속
- 잘못된 후보: `개인 정보 및 데이터 설정`
- 검증 결과: `wrong_destination`, `semantic_distance_increased`
- 복구: `back()` 성공, 잘못된 후보 금지
- 이후 진입: `추가 회원 자리 구매` 화면
- 일반 멤버십 가입 성공 판정: 하지 않음
- 위험한 구매 확정 자동 실행: 0건

`추가 회원 자리 구매`는 이미 활성 멤버십인 계정의 부가 구매 기능이므로 일반
`membership.join`의 목적지로 승격하지 않는다. 세션 진행 중 ADB 연결이 끊겨 두 세션을
모두 `stopped`로 닫았으며 연결 오류를 탐색 실패로 기록하지 않았다.

## 90% viewport 스크롤

새 구현은 모델이나 Solar/VLM이 좌표를 만들지 않는다.

1. Accessibility에서 현재 보이는 실제 scrollable node를 찾는다.
2. 그 노드의 화면 경계를 물리 디스플레이 경계로 자른다.
3. scrollable viewport 높이의 정확히 `0.90`에 해당하는 표준 swipe를 Executor가 만든다.
4. 아래 방향은 아래 95% 지점에서 위 5% 지점으로, 위 방향은 그 반대로 이동한다.
5. 약 10%만 겹치게 남겨 문맥을 유지한다.
6. gesture 예약 뒤 기존 DroidRun 관찰로 실제 화면 변화 여부를 다시 검증한다.

이 좌표는 허용 행동 `scroll(direction)`의 기기 측 구현 세부사항이며 현재 화면의
Accessibility 경계에서 결정된다. 모델이 임의 좌표를 생성하거나 클릭하는 경로는 없다.

구성 변경:

- `android:canPerformGestures=true`
- `ViewportScrollPlan.VIEWPORT_FRACTION=0.90`
- 실행 로그에 `viewport_fraction=0.9` 기록
- gesture를 예약하지 못하면 기존 작은 스크롤로 폴백하지 않고 실행 실패로 기록

## ADB 단절 자동 일시중지

ADB로 시작한 탐색에는 15초짜리 짧은 lease를 요구한다.

- 숨김 PowerShell 감시기가 고정된 기기 serial을 5초마다 확인한다.
- 연결 중에는 DUMP 권한 receiver로 heartbeat만 보낸다.
- 연결이 끊기면 heartbeat를 중단하고 상태를 `paused / adb_disconnected`로 기록한다.
- Executor는 매 판단 전과 지연된 모델 응답을 실행하기 직전에 lease를 재검사한다.
- lease가 만료되면 행동과 DB 수집을 중지하고 자동 재개하지 않는다.
- 연결 복구 후 새 목표 시작 또는 설치 검증을 명시적으로 수행해야 재개된다.

수동으로 기기에서 시작한 탐색은 ADB lease를 요구하지 않는다. 이 규칙은 실기기 수집용
ADB 시작 경로에만 적용된다.

## 오프라인 검증

- Android `testDebugUnitTest`: passed
- `ViewportScrollPlanTest`: 90% 거리, 양방향, 화면 경계 clipping, 작은 영역 거부 통과
- Android `assembleDebug`: passed
- PowerShell 3개 스크립트 parser: passed
- 감시기 단절 분기: `paused`, `reason=adb_disconnected`, `auto_resume=false`
- Navigation API 단위 테스트: 10/10 passed
- 커버리지 계약: 55셀, 최종 6셀, 미완료 49셀, 위험 자동 행동 0건

## 재연결 후 필수 검증

현재 기기가 ADB에서 분리돼 있어 다음 항목은 아직 `pending`이다.

1. `scripts/Install-NavigationExecutor.ps1`로 새 APK 설치
2. 접근성 서비스 자동 복원과 실제 bound 확인
3. Netflix 계정 WebView에서 로그의 `viewport_fraction=0.9` 확인
4. 스크롤 전후 화면이 약 10%만 겹치고 한 번에 다음 정보 구간으로 이동하는지 확인
5. 케이블 단절 시 15초 이내 추가 행동 없이 `paused`가 되는지 확인
6. 연결 복구 후 자동 재개되지 않는지 확인

이 실기기 검증 전에는 Netflix `membership.join`을 완료 상태로 바꾸거나 새 Runtime 경험을
승격하지 않는다.
