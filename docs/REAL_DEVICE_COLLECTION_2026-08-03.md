# 실기기 Decision Memory 수집 보고 — 2026-08-03

## 결론

제주항공 `membership.join` 최종 실기기 탐색은 4개 안전 행동, 약 14.1초로 목적지에
도달했다. 네 행동 모두 DB/Python fast path였고 화면별 후보 판단을 위한 Solar 호출은
0회였다. 기존 실행에서 발생한 반복·무변화·잘못된 클릭은 최종 세션에서 0건이며,
목적지 화면의 의미 일치도는 `0.156 → 0.880`으로 상승했다. 위험 행동 자동 실행은
0건이다.

두 번째 collection 앱인 YouTube에서는 `내 페이지` 진입 뒤 계정이 이미
`Premium 회원`임을 관찰했다. 이는 가입 성공 경로나 탐색 실패가 아니므로
`already_satisfied` 계정 상태 경계로 분리했다. 최종 세션은 안전 클릭 1회 뒤 즉시
중지됐고, 해당 후보를 실패 후보로 금지하지 않았다. 이 계정으로는 신규 가입 흐름을
검증할 수 없어 Decision DB 성공 경험으로 승격하지 않았다.

세 번째 collection 앱인 Coupang도 계정이 이미 `WOW! 혜택 이용중`이었다. 첫
진단에서는 `마이쿠팡`을 반복 클릭했지만, 활성 혜택 상태를 별도 경계로 추가한 최종
세션에서는 `마이쿠팡` 1회 클릭 후 추가 UI 행동 없이 `already_satisfied`로
중지했다. 화면별 Solar 후보 판단과 위험 행동은 모두 0회였다.

다만 이 결과는 collection 앱 세 개의 구조 수정·계정 상태 경계 검증이다. 고정
74건 replay의 전체 다음 행동 정확도는 여전히 `0.4286`이므로, 처음 보는 앱의 범용
성능이 증명됐다고 볼 수 없다. 이번 Runtime 기록은 Decision DB 크기를 늘리지 않고
재현 검증 자료로만 보존한다.

## 평가 분리

고정 manifest: `navigation-app-split-v1-20260803`

| split | 앱 | 상태 |
|---|---|---|
| collection (8) | Coupang, YouTube, Netflix, Jeju Air, Baemin, X, Discord, Samsung Launcher | 수집 허용 |
| validation (2) | KB Insurance, NH Nonghyup Property and Casualty Insurance | 반복 평가 전용 |
| locked_holdout (3) | Instagram, Postype, ChatGPT | 접근하지 않음 |

locked holdout 접근 허용은 `false`이며 이번 작업에서 세 앱을 실행하거나 결과를 보지
않았다.

## 앱별 진행

| 앱 | 목적 | 결과 | 행동 수 | 소요 시간 |
|---|---|---|---:|---:|
| Jeju Air 초기 성공 | `membership.join` | `reached` | 4 | 125.2초 |
| Jeju Air 최종 fast path | `membership.join` | `reached` | 4 | 약 14.1초 |
| YouTube 최종 계정 상태 경계 | `membership.join` | `already_satisfied` 후 중지 | 1 | 약 1.8초 |
| Coupang 최종 계정 상태 경계 | `membership.join` | `already_satisfied` 후 중지 | 1 클릭 | 약 6.5초 |
| Netflix | `membership.join` | 검은 화면 지속, 앱 렌더링 오류로 수집 제외 | 0 | - |
| 나머지 collection 앱 | 미실행 | 다음 부족 영역 선정 대기 | 0 | - |

최종 성공 세션: `navs_a22e45b9ba144c58b56e08707c0149f9`

1. 홈 → `마이페이지`
2. 마이페이지 → `전체메뉴 열기`
3. 전체메뉴 → 상위 `J 멤버스` 영역
4. 펼쳐진 메뉴 → 실제 하위 `J 멤버스`
5. 행동 후 `회원 전용 혜택 / 회원 가입하고 혜택 받자` 화면을 관찰하고 종료

`마이페이지`, `전체메뉴 열기`, 상위 `J 멤버스`는 유일하고 안전한 중간 역할
fast path로 선택했다. 상위 메뉴가 펼쳐진 뒤에는 직전 expander와 같은 이름이면서
부모 문맥도 자기 라벨과 일치하는 실제 하위 `J 멤버스`를 구조적 continuation
fast path로 선택했다. 행동 후 DroidRun식 검증이 `destination_reached`를 기록하고
Executor가 종료했다.

## 이번 변경

- 무료 회원형 멤버십의 혜택 안내 화면을 별도 `membership.join` Destination
  Signature로 추가했다.
- 문구 전체 일치가 아니라 정규화된 의미 토큰 조합으로 Signature를 평가한다.
- 로그인 화면의 비밀번호 입력란과 `회원가입` 링크를 가입 완료 경계로 오인하지 않도록
  `account.signup` 경계를 강화했다.
- 선택된 탭, 비활성 후보, 동일 화면 재방문, 중지 후 늦게 도착한 API 응답을 차단했다.
- 기능 카탈로그에 붙여 쓴 `전체메뉴`를 `navigation.menu`의 고신뢰 별칭으로 추가했다.
- 화면 전체가 합쳐진 긴 Accessibility 라벨은 단일 fast path 후보에서 제외했다.
- 성공적으로 펼친 후보와 같은 라벨의 안전한 하위 후보가 새로 나타난 경우에만
  구조적 continuation fast path를 사용한다.
- 휴대폰·유선·대표번호를 모두 `[phone]`으로 마스킹하고 기존 Runtime DB도 백업 후
  정화했다.
- `@handle`을 `[account]`로 마스킹하며, YouTube 계정 화면에서 발견한 기존 raw
  handle도 백업 후 정화했다.
- 활성 멤버십 문구를 `membership.join` 목적지로 오인하지 않도록 금지 특징을
  추가하고, 행동 전·후 모두 `already_satisfied` 경계를 우선 평가한다.
- 이미 가입된 상태에 도달한 안전 후보는 `wrong_destination`이나 금지 후보로
  기록하지 않는다.
- `WOW! 혜택 이용중`처럼 서비스마다 다른 활성 멤버십 표현을 가입 완료와 분리한다.
- 부분 마스킹된 한국어 이름은 `[account]`, 원화·달러 등 통화 금액은 `[amount]`로
  일반화해 계정 화면의 개인정보와 잔액을 저장하지 않는다.

N100 Decision DB는 기존 파일을 덮어쓰지 않고
`navigation-decision-v2-1f242fa8.sqlite`로 새로 생성했다. 이전 DB 파일도 그대로
보존했다. v1/v2 무결성 검사를 모두 통과했고 Destination Signature는 6개에서 7개,
Affordance 별칭은 80개에서 81개가 됐다.

## Runtime 기록과 승격

| 항목 | 작업 전 | 작업 후 | 변화 |
|---|---:|---:|---:|
| sessions | 32 | 44 | +12 |
| decisions | 59 | 93 | +34 |
| observations | 48 | 81 | +33 |
| 완전한 실행·관찰 step | 43 | 76 | +33 |
| 화면 후보 | 1,603 | 2,904 | +1,301 |
| pending 실패 수정 제안 | 7 | 12 | +5 |

- 새 Runtime 완전 실행·관찰 경험: 33개
- 최종 제주항공 성공 trajectory와 YouTube·Coupang 계정 상태 경계에 포함된 경험: 7개
- incomplete decision: 1개
- Decision DB 승격 후보: 0개
- 실제 승격: 0개
- collection 앱 진단 replay 또는 계정 제약으로 승격에서 제외: 33개
- 개인정보 때문에 승격에서 제외: 0개

추가 실행은 collection 앱에서 수정 전후 동작을 비교한 진단 replay다. 마지막
전환은 새 Signature·fast path·계정 상태 경계 검증에는 유효하지만 범용 성공 경험은 아니므로
Decision DB에 자동 승격하지 않았다.

## 실패·복구·충돌

- 기존 세션에서는 선택된 상위 `J 멤버스`를 다시 눌러 `no_change`가 발생했고,
  혜택 화면에서 `전체메뉴 열기`를 눌러 A↔B 반복이 생겼다.
- 중간 실험 세션 `navs_3dde8e3c52974e3e90efb740108db167`에서는 반복 후보를
  강등했지만 Solar가 `J 멤버스 혜택존`을 골라 `wrong_destination`이 발생했다.
  데이터를 더 수집하지 않고 구조적 continuation 규칙으로 수정했다.
- 후보의 `selected/clickable/enabled` 상태를 보존하고 선택된 탭을 강등해 같은 오동작을
  막았다.
- 동일 화면 세 번째 방문 전 `stop_for_user()`를 반환하는 교차 화면 반복 차단을
  추가했다.
- 중지 직후 늦게 도착한 API 응답은 서버에 결정만 남기고 실제 UI 행동을 실행하지
  않는 것을 별도 smoke test로 확인했다.
- 진단 중 `uiautomator dump`가 삼성 접근성 서비스를 재연결한 세션
  `navs_7a0f18c6c7304d4a949c9e83723cd618`은 서버에서 `stopped` 처리했다. 이는 탐색
  실패나 `not_supported`로 기록하지 않았고 승격에서도 제외했다.
- 제주항공 최종 세션 Fast Path는 4/4였다. 의미 역할 fast path 3회와 구조적 continuation
  fast path 1회이며, 화면별 Solar 후보 판단은 0회였다.
- YouTube 첫 진단에서는 콘텐츠의 `작업 메뉴`를 전역 메뉴로 오인해 Shorts 후보를
  눌렀다. 콘텐츠 문맥의 overflow 아이콘을 `navigation.menu`에서 제외한 뒤
  `내 페이지`를 올바르게 선택했다.
- 다음 진단에서는 `Premium 회원` 문구를 가입 목적지로 잘못 판정했다. 활성 상태를
  목적지 금지 특징으로 추가한 뒤에는 목적지 오판이 사라졌다.
- 첫 `already_satisfied` 구현에서는 올바른 `내 페이지` 이동을 먼저
  `wrong_destination`으로 기록하는 순서 오류가 드러났다. 행동 후 계정 상태 경계를
  우선 평가하도록 고쳤고, 잘못 생성된 pending 수정 제안 1건은 삭제하지 않고
  `rejected` 처리해 감사 이력을 보존했다.
- 최종 YouTube 세션 `navs_4add085e43b54c808ad3f70b76a9f50d`는 `내 페이지` 클릭
  1회 뒤 `blocked/already_satisfied`, `progress=advanced`, 후보 금지 0건으로 종료됐다.
- Coupang 첫 세션 `navs_df8b38f66049476ea6e7f4847cc4bf81`에서는 Solar가 이미
  진입한 `마이쿠팡`을 다시 선택해 `no_change`가 발생했다. 화면의
  `WOW! 혜택 이용중`을 활성 멤버십 경계로 추가해 반복 원인을 제거했다.
- 최종 Coupang 세션 `navs_5e1847b33ae8486eb7b7c202a47bebcd`는 `마이쿠팡` 클릭 뒤
  `python_goal_already_satisfied`로 종료됐다. Solar 호출 0회, 반복 클릭 0건, 후보
  금지 0건이다. 수정 전 자동 제안 1건은 최신 증거로 `rejected` 처리했다.
- Netflix는 `SignupNativeActivity`가 20초 이상 검은 화면을 유지했다. 후보가
  렌더링되지 않아 Executor를 시작하지 않았으며 탐색 실패나 `not_supported`로
  기록하지 않았다.

## 개인정보와 화면 유지

Runtime DB 정화 전 엄격한 전화번호 규칙에 해당하는 콘텐츠 hit 380개를 확인했고,
백업 후 0개로 줄였다. SQLite `quick_check=ok`, 외래키 오류 0건이다. 세션·결정·후보
ID는 변경하지 않았다.

YouTube 계정 화면에서 raw `@handle` 4개를 추가로 확인해 `[account]`로 마스킹했다.
정화 전 백업과 JSON 보고서를 보존했다. 최종 YouTube 세션 뒤 후보·화면 payload의
`@` 잔존은 각각 0건이며 `quick_check=ok`, 외래키 오류 0건이다.

Coupang 계정 화면에서 부분 마스킹 이름과 절약액·잔액을 확인했다. 새 개인정보 규칙을
적용하기 전 별도 백업을 만들고 민감 패턴 hit 380건을 0건으로 정화했다. 최종 세션은
처음부터 `[account]`, `[amount]`로 기록됐고 raw 이름·금액 잔존은 0건이다.

최종 세션 뒤 재검사에서도 민감정보 hit는 0개였고 변경된 행도 0개였다. 별도 백업을
남긴 뒤 SQLite `quick_check=ok`, 외래키 오류 0건을 다시 확인했다.

탐색 중에는 60초 좌표 터치를 넣지 않았다. 대상 앱의 행동으로 오인될 수 있기 때문이다.
대신 Executor `SCREEN_DIM_WAKE_LOCK`, ADB `stay_on_while_plugged_in=2`를 사용했다.
탐색 종료 후 WakeLock은 정상 해제됐고 USB 화면 유지 설정은 남아 있다.

## 작은 평가

| 지표 | 변경 전 | 변경 후 |
|---|---:|---:|
| 첫 행동 정확도 | 0.7778 | 0.7778 |
| 전체 다음 행동 정확도 | 0.4286 | 0.4286 |
| 실패 클릭 회피율 | 0.8182 | 0.9091 |
| 위험 행동 자동 실행 | 0 | 0 |
| 제주항공 목적지 도달 | 반복으로 수동 중지 | 4행동 `reached` |
| 반복 화면 | 발생 | 0 |
| 잘못된 클릭 | 발생 | 0 |
| 화면별 Solar 후보 판단 | 3회 이상 | 0회 |
| 실기기 소요 시간 | 125.2초 | 약 14.1초 |
| YouTube 활성 멤버십 오판 | 가입 목적지로 오인 | `already_satisfied`로 안전 중지 |
| Coupang 활성 멤버십 반복 | `마이쿠팡` 재클릭 후 무변화 | 1회 진입 후 안전 중지 |

고정 replay 성능은 악화되지 않았지만 개선되지도 않았다. 따라서 정적 데이터를 대량
추가하지 않는다. 다음 수집은 `membership.join`의 두 번째 앱 계열처럼 현재 DB에 없는
의미적 구조를 우선하고, 그 뒤 validation replay를 다시 실행한다.

## 검증된 배포

- N100 배포 코드: `8d978d3`
- Decision DB SHA-256:
  `1f242fa8646e830abea0a90c2e58f36b43f7a6697a41993df88e0512d9a299b4`
- N100 API: `ready=true`, `research_models_ready=true`
- GitHub `main`, `agent/navigation-db-redesign`: Navigation DB Redesign Checks 성공
