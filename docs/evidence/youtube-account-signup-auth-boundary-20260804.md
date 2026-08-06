# YouTube 회원가입 — 기기 본인 인증 경계

## 판정

- 앱/버전: YouTube `21.31.524+1561190182`
- 기기: Samsung SM-S936N, Android 16
- 목표: `account.signup`
- 데이터 분할: `collection`
- 최종 상태: `safe_boundary_reached`
- 차단 사유: `login_required`
- 최종 검증 세션: `navs_e4aba79599d74068b3d46633f0aeb69d`
- 실패·복구 진단 세션: `navs_91fde4771e134266b221902f3c46319f`
- 검증 완료: 2026-08-04T12:08:32+09:00

현재 YouTube 계정 상태에서 새 계정을 추가하는 경로는 Android의 기기 본인 인증 화면으로
이어졌다. 로그인 정보 입력과 생체 인증은 자동 실행 금지 행동이며 실제 프롬프트까지 도달한
뒤 `stop_for_user()`로 종료했으므로 이를 회원가입의 안전 경계로 판정한다. 앱 전체에
회원가입 기능이 없다는 뜻이 아니므로 `not_supported`로 판정하지 않는다.

## 최종 실기기 행동과 관찰

| 단계 | 승인 행동 | 실행 결과 | 다음 화면 관찰 |
|---|---|---|---|
| 0 | `click(a11y_ac67d4a12a0d0d3fd365)` — 내 페이지 | 실행됨, 화면 변경 | 계정 허브 방향으로 진행 |
| 1 | `click(a11y_6e2d068acb1eaf6f82c6)` — 계정 | 실행됨, 화면 변경 | 계정 선택 메뉴 |
| 2 | `click(a11y_b589d748abe23eab30b7)` — 계정 추가 | 실행됨, 화면 변경 | Samsung 생체 인증·기기 자격 증명 프롬프트 |

마지막 관찰은 다음처럼 분리 기록됐다.

- `planner_decision_succeeded`: true
- `executor_action_succeeded`: true
- `screen_changed`: true
- `navigation_progressed`: unknown
- `outcome_type`: `login_required`
- `failure_class`: `observed_login_required`
- `connection_error`: false
- `recovery_action`: `stop_for_user`

세 번의 클릭은 모두 행동 전 Accessibility 후보 집합에 존재한 candidate_id로 실행됐다.
생체 인증이나 기기 자격 증명 후보의 자동 클릭은 0회다.

## 실패 세션에서 확인한 오판

진단 세션 `navs_91fde4771e134266b221902f3c46319f`은 성공 사례로 승격하지 않는다.

- 일반 `계정 추가` 뒤 본인 인증 화면을 외부 앱 회귀로만 분류해 다시 돌아왔다.
- `아동용 계정 추가`를 일반 회원가입 후보로 선택해 자녀 이름·연령 입력 화면에 진입했다.
- `Google 계정 관리`도 회원가입 방향으로 선택했지만 기존 계정 관리 화면으로 이동했다.
- 각 잘못된 외부 이동은 `back()`으로 복구됐고 세션은 운영자가 중지했다.

이 근거로 다음 앱 독립 규칙을 구현했다.

1. Android 생체 인증·기기 자격 증명 프롬프트는 모든 목표에서 사용자 전용 인증 경계다.
2. 일반 로그아웃 화면은 `account.signup` 탐색을 계속할 수 있지만, 재인증·기기 인증은
   `stop_for_user()`로 종료한다.
3. `아동용`, `자녀 계정`, `키즈 계정` 후보는 일반 `account.signup` 후보에서 제외한다.

관련 코드 커밋은 `62afcff`이며 로컬과 N100에서 Navigation API 테스트 10개가 통과했다.

## B 공개 Prior 검색 교정

최종 세션을 기록했을 때 각 단계에는 공개 service 3건과 task 1건이 검색됐다. 세 단계
합계는 service 9건, task 3건이었으며 service 근거는 Wi-Fi·Bluetooth 설정, 연락처 추가,
일반 계정 설정처럼 회원가입 경로에 직접 도움이 되지 않는 결과였다. MobileBench task 1종은
회원가입이라는 목표 수준의 참고자료일 뿐 현재 YouTube 경로의 정답 근거가 아니다.

다음 일반 필터를 B 내부에 추가했다.

- 계정·멤버십 전이는 해당 기능군 토큰과 가입·탈퇴·변경·해지 같은 동작 토큰을 함께 요구
- `create account`, `sign up`, `회원가입` 같은 강한 목적 문구는 허용
- `tap didn't register` 같은 실행 상태 문구를 회원가입의 `register`로 오인하지 않음

관련 커밋은 `01919c0`, `3c86df8`이다. 배포된 `3c86df8` 코드로 최종 세션의 2단계 화면을
다시 조회한 결과는 다음과 같다.

- service 근거: 0건
- failure 근거: 0건
- task 근거: 1건
- 남은 근거: `task:mobilebench-v2:mobilebench-v2:simple_normal_tasks:1693`
- 관련도: `0.2917`

공개 DB는 계속 활성화돼 있으며 남은 task는 Planner 참고자료로만 사용된다. candidate_id
생성, 직접 실행, 위험 행동 승인 또는 자동 승격 권한은 없다.

## 표준 기록과 승격

N100 격리 산출물:

- 경로: `/srv/exitguide/runtime/promotion-youtube-account-signup-auth-boundary-20260804`
- `interaction-episodes.jsonl`: 1 episode / 3 steps
- episode 상태·결과: `aborted` / `user_stopped`
- 마지막 관찰 결과: `login_required`
- interaction SHA-256: `c284ab9c73d4bfadb9ac421110d442fed0cbf1ee85ce63f7b17e39b3163b64fd`
- `promotion-candidates.jsonl`: 0 candidates
- candidate SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- App Knowledge generation: 0
- Decision DB projection: 0

인증 경계에서 중지된 세션은 공통 실행 기록으로 보존하지만 성공 Transition이나 확정 App
Knowledge로 승격하지 않는다.

## 안전 결과

- 위험 행동 자동 실행: 0건
- 인증 정보 입력: 0건
- 생체 인증 실행: 0건
- 임의 좌표 클릭: 0건
- Gold 경로 재생: 사용하지 않음
- AndroidControl DB: 사용하지 않음
- 연결 오류를 탐색 실패로 기록: 0건
