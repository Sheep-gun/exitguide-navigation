# 실기기 Decision Memory 수집 보고 — 2026-08-03

## 결론

제주항공 `membership.join` 실기기 탐색은 4개 안전 행동으로 목적지에 도달했다.
기존 실행에서 발생한 `J 멤버스 → 전체메뉴 → J 멤버스` 반복은 재현되지 않았고,
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
| Jeju Air | `membership.join` | `reached` | 4 | 125.2초 |
| 나머지 collection 앱 | 미실행 | 다음 부족 영역 선정 대기 | 0 | - |

성공 세션: `navs_5b827b97e6d24527ab3339700b6e5eaa`

1. 홈 → `마이페이지`
2. 마이페이지 → `전체메뉴 열기`
3. 전체메뉴 → 상위 `J 멤버스` 영역
4. 펼쳐진 메뉴 → 실제 하위 `J 멤버스`
5. 행동 후 `회원 전용 혜택 / 회원 가입하고 혜택 받자` 화면을 관찰하고 종료

앞의 세 행동은 Solar Pro 3가 선택했다. 마지막 행동에서는 Solar 결과를 그대로 쓰지
않고 후보 상태와 Decision Memory fallback이 실제 하위 후보를 선택했다. 행동 후
DroidRun식 검증이 `destination_reached`를 기록하고 Executor가 종료했다.

## 이번 변경

- 무료 회원형 멤버십의 혜택 안내 화면을 별도 `membership.join` Destination
  Signature로 추가했다.
- 문구 전체 일치가 아니라 정규화된 의미 토큰 조합으로 Signature를 평가한다.
- 로그인 화면의 비밀번호 입력란과 `회원가입` 링크를 가입 완료 경계로 오인하지 않도록
  `account.signup` 경계를 강화했다.
- 선택된 탭, 비활성 후보, 동일 화면 재방문, 중지 후 늦게 도착한 API 응답을 차단했다.
- 휴대폰·유선·대표번호를 모두 `[phone]`으로 마스킹하고 기존 Runtime DB도 백업 후
  정화했다.

N100 Decision DB는 기존 파일을 덮어쓰지 않고
`navigation-decision-v2-2b18725e.sqlite`로 새로 생성했다. v1/v2 무결성 검사를 모두
통과했고 Destination Signature는 6개에서 7개가 됐다.

## Runtime 기록과 승격

| 항목 | 작업 전 | 작업 후 | 변화 |
|---|---:|---:|---:|
| sessions | 32 | 34 | +2 |
| decisions | 59 | 65 | +6 |
| observations | 48 | 53 | +5 |
| 완전한 실행·관찰 step | 43 | 48 | +5 |
| 화면 후보 | 1,603 | 1,801 | +198 |
| pending 실패 수정 제안 | 7 | 7 | 0 |

- 새 Runtime 유효 경험: 5개
- 성공 trajectory에 포함된 경험: 4개
- incomplete decision: 1개
- Decision DB 승격 후보: 0개
- 실제 승격: 0개
- 중복으로 제외: 5개
- 개인정보 때문에 승격에서 제외: 0개

5개 완전 경험은 이미 존재하는 동일 앱·동일 화면 전환의 재현이다. 마지막 전환은 새
Signature의 판정 검증에는 유효하지만 새로운 앱 경험은 아니므로 자동 승격하지 않았다.

## 실패·복구·충돌

- 기존 세션에서는 선택된 상위 `J 멤버스`를 다시 눌러 `no_change`가 발생했고,
  혜택 화면에서 `전체메뉴 열기`를 눌러 A↔B 반복이 생겼다.
- 후보의 `selected/clickable/enabled` 상태를 보존하고 선택된 탭을 강등해 같은 오동작을
  막았다.
- 동일 화면 세 번째 방문 전 `stop_for_user()`를 반환하는 교차 화면 반복 차단을
  추가했다.
- 중지 직후 늦게 도착한 API 응답은 서버에 결정만 남기고 실제 UI 행동을 실행하지
  않는 것을 별도 smoke test로 확인했다.
- 진단 중 `uiautomator dump`가 삼성 접근성 서비스를 재연결한 세션
  `navs_7a0f18c6c7304d4a949c9e83723cd618`은 서버에서 `stopped` 처리했다. 이는 탐색
  실패나 `not_supported`로 기록하지 않았고 승격에서도 제외했다.
- Fast Path는 0/4였다. 모호한 처음 세 화면은 Solar로 보냈고 마지막 화면은
  `decision_memory_fallback`으로 처리했다.

## 개인정보와 화면 유지

Runtime DB 정화 전 엄격한 전화번호 규칙에 해당하는 콘텐츠 hit 380개를 확인했고,
백업 후 0개로 줄였다. SQLite `quick_check=ok`, 외래키 오류 0건이다. 세션·결정·후보
ID는 변경하지 않았다.

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

고정 replay 성능은 악화되지 않았지만 개선되지도 않았다. 따라서 정적 데이터를 대량
추가하지 않는다. 다음 수집은 `membership.join`의 두 번째 앱 계열처럼 현재 DB에 없는
의미적 구조를 우선하고, 그 뒤 validation replay를 다시 실행한다.

## 검증된 배포

- 코드: `d7be8ef4a7cb5424014c57895885a3dadf93fa68`
- Decision DB SHA-256:
  `2b18725e571aff4ffeae252c311d5acee058f5009bfe6ee95199926b133686ed`
- N100 API: `ready=true`, `research_models_ready=true`
- GitHub `main`, `agent/navigation-db-redesign`: Navigation DB Redesign Checks 성공
