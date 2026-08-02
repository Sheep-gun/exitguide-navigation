# 실기기 Decision Memory 수집 보고 — 2026-08-03

## 결론

제주항공 `membership.join` 최종 실기기 탐색은 4개 안전 행동, 약 14.1초로 목적지에
도달했다. 네 행동 모두 DB/Python fast path였고 화면별 후보 판단을 위한 Solar 호출은
0회였다. 기존 실행에서 발생한 반복·무변화·잘못된 클릭은 최종 세션에서 0건이며,
목적지 화면의 의미 일치도는 `0.156 → 0.880`으로 상승했다. 위험 행동 자동 실행은
0건이다.

다만 이 결과는 기존 증거가 있는 collection 앱 한 개의 구조 수정 검증이다. 고정
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

N100 Decision DB는 기존 파일을 덮어쓰지 않고
`navigation-decision-v2-b5bc2b4f.sqlite`로 새로 생성했다. 이전 DB 파일도 그대로
보존했다. v1/v2 무결성 검사를 모두 통과했고 Destination Signature는 6개에서 7개,
Affordance 별칭은 80개에서 81개가 됐다.

## Runtime 기록과 승격

| 항목 | 작업 전 | 작업 후 | 변화 |
|---|---:|---:|---:|
| sessions | 32 | 37 | +5 |
| decisions | 59 | 80 | +21 |
| observations | 48 | 68 | +20 |
| 완전한 실행·관찰 step | 43 | 63 | +20 |
| 화면 후보 | 1,603 | 2,370 | +767 |
| pending 실패 수정 제안 | 7 | 10 | +3 |

- 새 Runtime 완전 실행·관찰 경험: 20개
- 최종 성공 trajectory에 포함된 경험: 4개
- incomplete decision: 1개
- Decision DB 승격 후보: 0개
- 실제 승격: 0개
- 동일 collection 앱 진단 replay로 승격에서 제외: 20개
- 개인정보 때문에 승격에서 제외: 0개

추가 실행은 동일 collection 앱에서 수정 전후 동작을 비교한 진단 replay다. 마지막
전환은 새 Signature와 fast path 검증에는 유효하지만 새로운 앱 경험은 아니므로
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
- 최종 세션 Fast Path는 4/4였다. 의미 역할 fast path 3회와 구조적 continuation
  fast path 1회이며, 화면별 Solar 후보 판단은 0회였다.

## 개인정보와 화면 유지

Runtime DB 정화 전 엄격한 전화번호 규칙에 해당하는 콘텐츠 hit 380개를 확인했고,
백업 후 0개로 줄였다. SQLite `quick_check=ok`, 외래키 오류 0건이다. 세션·결정·후보
ID는 변경하지 않았다.

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
| 실패 클릭 회피율 | 0.8182 | 0.8182 |
| 위험 행동 자동 실행 | 0 | 0 |
| 제주항공 목적지 도달 | 반복으로 수동 중지 | 4행동 `reached` |
| 반복 화면 | 발생 | 0 |
| 잘못된 클릭 | 발생 | 0 |
| 화면별 Solar 후보 판단 | 3회 이상 | 0회 |
| 실기기 소요 시간 | 125.2초 | 약 14.1초 |

고정 replay 성능은 악화되지 않았지만 개선되지도 않았다. 따라서 정적 데이터를 대량
추가하지 않는다. 다음 수집은 `membership.join`의 두 번째 앱 계열처럼 현재 DB에 없는
의미적 구조를 우선하고, 그 뒤 validation replay를 다시 실행한다.

## 검증된 배포

- 코드: `068a857e654c70b9b7eeb02ac58e7253e35f8dc7`
- Decision DB SHA-256:
  `b5bc2b4f536a4fdc3a31ac5aaf00a3bf17a629cbfb500d512c265de76ddec946`
- N100 API: `ready=true`, `research_models_ready=true`
- GitHub `main`, `agent/navigation-db-redesign`: Navigation DB Redesign Checks 성공
