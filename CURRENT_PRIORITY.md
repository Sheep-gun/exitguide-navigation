# ExitGuide Navigation Current Priority

status: blocked
phase: device_validation
updated_at: 2026-08-04T12:49:00+09:00
priority: B 고정 아키텍처로 11개 앱 × 5개 목표의 실기기 커버리지 55셀 완성
decision_db_collection: paused
next_action: Samsung SM-S936N을 ADB로 다시 연결한 뒤 commit 07280a8 APK에 scripts/Install-NavigationExecutor.ps1을 실행하고 접근성 bound·90% 실제 스크롤·ADB lease 중지를 검증한 후 Netflix membership.join B 세션을 새로 시작한다.
verification_started_at: 2026-08-04T05:35:00+09:00
verification_completed_at: pending
verified_device: Samsung SM-S936N, Android 16
verified_apps: YouTube 21.31.524+1561190182; Netflix 9.77.0 build 9 64328+64328; X 12.12.0-release.0+312120000; TVING 26.31.02+20263102
baseline_commit: `a4a47c327468a1670caec6fdcd56be01a0923fc1`
integration_commit: `3c86df8c42dcb22bf94b0529a0777bcba71a7bda`
deployed_commit: `3c86df8c42dcb22bf94b0529a0777bcba71a7bda`

## 고정 정책

- architecture: `B fixed`
- public_navigation_prior: `enabled`, 운영 확인값 `true`
- ab_winner_comparison: `disabled`
- evaluation_basis: B 절대 지표, 고정 replay, locked holdout 회귀
- public_role: Planner/Solar 참고 근거만 허용
- runtime_execution_allowed_for_public_data: false
- canonical_promotion_allowed_for_public_data: false
- arbitrary_coordinate_click: forbidden
- AndroidControl_runtime_use: forbidden
- Gold_path_replay: forbidden
- dangerous_action_auto_execution: forbidden

과거 TVING OFF/ON 수치는 삭제하지 않고 검색 오류 진단 자료로만 보존한다. A를 기준선이나
승자로 사용하지 않으며, 무관 검색과 오판은 공개 Prior를 끄지 않고 B 내부에서 수정한다.

## 전체 커버리지 목표

- 대상: 사용자 지정 10개 앱 + TVING
- 목표: `account.signup`, `account.delete`, `membership.join`, `membership.change`, `membership.cancel`
- 완료 단위: 11개 앱 × 5개 목표 = 55셀
- 완료 상태: `destination_reached`, `safe_boundary_reached`, 근거 있는 `not_supported`, 근거 있는 `not_testable`
- 미완료 상태: `not_explored`, `in_progress`, 임시 연결·환경 오류
- locked holdout: Instagram, Postype, ChatGPT
- validation: TVING
- split_manifest: `db/navigation_coverage_split_v1.json`, 7 collection / 3 locked holdout / 1 TVING validation
- coverage_source: `db/navigation_goal_coverage_v1.json`
- coverage_document: `docs/NAVIGATION_GOAL_COVERAGE.md`
- current_coverage_scope: 11/11 앱, 55셀 계약 검증 통과; 최종 상태 6셀, 미완료 49셀
- pre_B_A_revalidation: YouTube·제주항공·쿠팡 `membership.join` 3셀을 `in_progress`로 복원

holdout 3개와 TVING 경험은 Decision DB 또는 App Knowledge로 승격하지 않는다.

## N100 운영 상태 — 2026-08-04 확인

- service: `exitguide-navigation-api.service`, active
- endpoint: `http://100.77.172.25:8100`
- ready: true
- code: `/home/kyle/exitguide/runtime/navigation-api-code-3c86df8-repo`
- deployed_git_head: `3c86df8c42dcb22bf94b0529a0777bcba71a7bda`
- public_prior.enabled: true
- public service episodes/transitions: 2,047 / 27,343
- public failure transitions: 2,737
- public task records: 570
- Decision DB: read-only patched immutable clone
- Runtime DB: coverage 전용, sessions 45, decisions 225, observations 198
- production split SHA-256: `9fa006adc74fc117c180ba051fd50e355fcb80ba6e970dd1e5b4a2fe43141142`
- production split counts: collection 8, validation 2, locked_holdout 3
- target coverage split SHA-256: `a26cb574561683fd973960df319f20e5f2ac205f4537a377f22289e7b8541bf5`
- target coverage split counts: collection 7, validation 1, locked_holdout 3
- target coverage Runtime: `/srv/exitguide/runtime/navigation-runtime-coverage-b-v1-a26cb574.sqlite` (운영 8100 쓰기 대상)
- planner: Solar Pro 4 selective, Solar Pro 3 fallback, EXAONE 4.5 selective

## Promotion pipeline v2

- implementation_commit: `0bdc4efbe8506673328537534cc9020a1192e9a1`
- generation_id: `generation_92648fdee0389cc62a911ac4`
- runtime_to_episode: implemented
- knowledge_promotion_contract: implemented
- independent_app_knowledge_generation: implemented
- Decision projection: implemented
- production Decision DB changed by staging validation: no
- unresolved_provenance: 기존 `uxa_*` 실기기 행 11개는 원본 common episode 근거가 필요해 보존 상태
- stopped_session_promotion: excluded by default; `navs_5cf09d3535864c049edff069feca21ea` retained only as aborted evidence
- Netflix promotion: interaction episodes 3개/14 steps, draft candidates 5개, accepted 0, generation 0
- candidate privacy: screen-wide account identifier redaction plus promotion-time defensive redaction

collection 경험은 다음 경로만 사용한다.

`Runtime DB → interaction-episode.v1 → knowledge-promotion.v1 → 반복 검증/승인 → App Knowledge generation → Decision DB projection`

Runtime DB에서 Decision DB로 직접 삽입하지 않는다.

## TVING validation 근거

- goal_id: `membership.join`
- app_package: `net.cj.cjhv.gs.tving`
- corrected_session: `navs_b83930dda4a74ab6a472a1e4735b468f`
- result: destination reached, match 0.8425
- candidate-ID clicks: 2
- final dangerous auto click: 0
- historical frozen OFF accuracy: 0.25
- historical frozen ON accuracy: 0.25
- historical_public_prior_improvement_proven: false
- runtime_winner_selection_from_ab: false
- patched Decision DB SHA-256: `3891d4cc4d44b10d5363e0134937eab215663f115cb0809d9e232bead82fd9c1`
- original Decision DB preserved SHA-256: `14c73a685ab7c915e9357ba6f99454e738f8f907d0b1abdf77c234825bb4478a`
- API unit tests: 10/10 passed
- promotion_allowed: false
- evidence: `docs/evidence/tving-public-prior-ab-20260804.md`

남은 TVING 복구 실패 사례는 `tving_my_bottom_recover_up`, `tving_settings_recover_back`이다.
이 사례는 B 내부 Retriever/복구 로직 수정 대상으로 보존한다.

## Android Executor와 APK 재설치 규칙

기존 Android 통합의 최초 7개 조건은 모두 passed이며 관련 코드·APK가 바뀌지 않으면
반복 검증하지 않는다.

APK 재설치 또는 교체 후 `scripts/Install-NavigationExecutor.ps1`을 실행하여 접근성
서비스를 자동 복원하고 실제 바인딩까지 확인한 뒤 탐색을 재개한다.

스크립트는 다음을 사용자 수동 조작 없이 확인해야 한다.

1. 단일 authorized ADB 기기
2. 기존 접근성 서비스 목록 보존
3. ExitGuide AccessibilityService enabled
4. `dumpsys accessibility` 실제 bound
5. Accessibility 노드 수집
6. candidate_id 생성
7. Navigation API 연결과 행동 전후 관찰 준비

OS가 ADB 복원을 명시적으로 차단하고 자동 재시도도 실패했을 때만 사용자 조작을 요청한다.

2026-08-04 실기기 재설치 검증:

- `adb install -r`: passed
- accessibility enabled/bound: passed
- preserved enabled service count: 2
- Accessibility nodes/candidates: 16/5
- B Navigation API ready/public prior: true/true
- Runtime sessions/decisions before and after diagnostic: 2/14, 변화 없음
- APK SHA-256: `BB88EE7B59007E6F1740FAF1B0B14FC1EE540BB1C98B8AE7EC434805AD68DC11`
- latest diagnostic request ID: `5da53191a71945da891cd992ab63b682`
- evidence: `docs/evidence/navigation-executor-auto-rebind-20260804.md`

## Netflix membership.cancel 안전 경계

- full traversal session: `navs_c69db94650b94d9ca9595c90dfa8bed4`
- post-fix revalidation session: `navs_20210f0aa6d34236b86f223d9861e827`
- final candidate: `a11y_d58ad4e05af6ee045883`, label `멤버십 해지`
- candidate safety: `risk_level=high`, `terminal=1`, `dangerous_final=1`
- final action: `stop_for_user`, executor action not executed
- outcome: `destination_reached`, session `reached`
- dangerous auto click: 0
- evidence: `docs/evidence/netflix-membership-cancel-safe-boundary-20260804.md`

## YouTube membership.cancel 안전 경계

- discovery session: `navs_24c124f68beb48b7af815e736097f43e`
- recovery/destination session: `navs_a08c470f59ed4a8ba5e172837fc70b3a`
- final safety session: `navs_e86d731eecd444c8b2fde916006b49d4`
- recovered wrong destination: expired channel membership, bounded `back()`
- active-plan evidence: `YouTube Premium`, `갱신일: 9월 3일`
- final candidate: `a11y_5d26c90368edb5f18c11`, label `취소`
- candidate safety: `risk_level=high`
- final action: `stop_for_user`, executor action not executed
- outcome: `destination_reached`, match `0.85`, session `reached`
- dangerous auto click: 0
- interaction episodes: 2 episodes / 5 steps
- promotion candidates: 1 draft, support 1; generation/projection 0
- evidence: `docs/evidence/youtube-membership-cancel-safe-boundary-20260804.md`

## YouTube membership.change 서비스 정책 경계

- corrected_session: `navs_5e40c4483d1b46068caa6c6ce039cb75`
- result: `not_testable`
- blocking_issue: `service_policy`
- candidate-ID clicks: 2
- observed path: 활성 Premium → 외부 구독 관리 게이트웨이 → 설정 → 예비 결제수단 관리
- plan-change candidates: `요금제 변경` 0, `플랜 변경` 0, `업그레이드` 0, `다운그레이드` 0
- executor actions succeeded: 4/4
- screen changes after clicks: 2/2
- connection errors: 0
- dangerous final auto click: 0
- false-success promotion: 0
- generic B tuning: 콘텐츠 탭 억제, 명시적 관리 게이트웨이 우선, 신뢰된 외부 관리 화면 계속 탐색, 결제수단 유지보수와 요금제 변경 분리
- local/N100 API unit tests for deployed code: 10/10 passed
- evidence: `docs/evidence/youtube-membership-change-service-policy-20260804.md`

## YouTube account.delete 목적지

- final_session: `navs_46bdd8ecf95547ddbc30af27da18c74a`
- result: `destination_reached`, match `0.82`
- observed_path: 내 페이지 → 계정 → Google 계정 관리 → 데이터 및 개인 정보 보호 → bounded scroll ×2
- final candidate: `a11y_55543879af66e5744fb2`, label `Google 계정 삭제`
- final candidate risk: `high`
- candidate-ID clicks / scroll / wait: 4 / 2 / 2
- executor actions succeeded: 8/8
- connection errors: 0
- dangerous final auto click: 0
- false-positive session excluded: `navs_6d3d968a5311433fb60f15ae9a0c4a16` (`YouTube 기록 자동 삭제` 오인)
- generic B tuning: provider handoff 진행 인정, 개인정보 토큰화 대응, privacy checkup 억제, 개인정보 허브 bounded scroll, 기록·활동 삭제와 계정 삭제 Signature 분리
- local/N100 API unit tests: 10/10 passed
- Android unit/build/install: passed; accessibility enabled/bound true
- interaction episodes: 1 episode / 8 steps
- promotion candidates: 5 draft, support 1; accepted/generation/projection 0
- evidence: `docs/evidence/youtube-account-delete-destination-20260804.md`

## YouTube account.signup 기기 인증 경계

- final_session: `navs_e4aba79599d74068b3d46633f0aeb69d`
- diagnostic_session: `navs_91fde4771e134266b221902f3c46319f`
- result: `not_testable`
- blocking_issue: `account_state`
- observed_path: 내 페이지 → 계정 → 계정 추가 → Samsung 생체 인증·기기 자격 증명
- candidate-ID clicks: 3
- executor actions succeeded: 3/3
- screen changes after clicks: 3/3
- final outcome/failure: `login_required` / `observed_login_required`
- final recovery: `stop_for_user`
- child-account candidate clicks in final session: 0
- biometric/credential actions: 0
- connection errors: 0
- dangerous final auto click: 0
- interaction episodes: 1 episode / 3 steps, `aborted` / `user_stopped`
- promotion candidates / generation / projection: 0 / 0 / 0
- B public-prior replay after filter: service 0, failure 0, task 1 (`0.2917`)
- generic B tuning: 기기 인증을 사용자 전용 경계로 분리, 일반 회원가입에서 아동용 계정 제외,
  계정 기능군+동작 토큰 필수화, `didn't register` 실행 상태 오인 제거
- local/N100 API unit tests for deployed code: 10/10 passed
- evidence: `docs/evidence/youtube-account-signup-auth-boundary-20260804.md`

YouTube `membership.join`은 B 고정 이전 A 기록으로 확인돼 재검증 대기로 되돌렸다.
나머지 4개 YouTube 목표는 근거 있는 최종 상태를 유지한다.

## 90% 스크롤·ADB 단절 자동 중지 — 실기기 재검증 대기

- implementation_commit: `07280a813ded8bcc77a34fe6b748e7d6a541abec`
- Android unit tests: passed
- APK build: passed
- APK SHA-256: `C9B64BF2D724533265B28BEBEE6E7A6B42078D0B797AB2C3C338AAF3E8D4A699`
- PowerShell parser: Install/Start/Stop/Monitor 4개 passed
- disconnected monitor branch: `paused`, `adb_disconnected`, `auto_resume=false`
- viewport scroll policy: Accessibility scrollable 영역 높이의 `0.90`, 예상 중복 약 `0.10`
- arbitrary model coordinates: 사용하지 않음
- ADB heartbeat: 5초 간격
- Executor ADB lease: 15초
- background execution: Install 스크립트가 device-idle whitelist와
  `RUN_ANY_IN_BACKGROUND=allow` 적용
- device deployment: pending
- real-device 90% overlap verification: pending
- real-device disconnect lease verification: pending
- evidence: `docs/evidence/android-executor-scroll-and-adb-pause-20260804.md`

Netflix `membership.join` 사전 수정 세션:

- first_session: `navs_4e35dab60e3d4d5eb14ff2242a3bde36`, stopped
- second_session: `navs_f1367c3dd19a441a9c4c6288dc9fce23`, stopped
- observed route: 홈 → 나의 넷플릭스 → 프로필 관리 → 계정 WebView
- old small scrolls: 4회 연속
- wrong click: `개인 정보 및 데이터 설정`
- failure/recovery: `wrong_destination` → `back()` 성공, 후보 금지
- non-goal branch: `추가 회원 자리 구매`, 일반 membership.join 성공으로 처리하지 않음
- dangerous purchase confirmation auto execution: 0
- promotion: 0
- stop reason: ADB disconnect; 탐색 실패로 변환하지 않음

현재 `adb devices -l`에는 기기가 0대다. 실기기 행동과 Decision DB 수집은 자동 일시중지
상태이며 연결만 복구돼도 자동 재개하지 않는다.

## 안전 불변조건

- 허용 행동: `click(candidate_id)`, `scroll(direction)`, `back()`, `wait_and_observe()`, `stop_for_user()`
- 최종 탈퇴·해지·결제·구독·개인정보 제출·로그인 정보 입력·약관 동의·외부 전송은 자동 실행하지 않는다.
- 위험 경계에서는 `stop_for_user()`를 반환한다.
- 연결 오류는 탐색 실패, 후보 없음, `not_supported`, `not_testable`로 기록하지 않는다.
- 모델이 반환한 candidate_id는 현재 화면 후보 집합에 실제 존재해야 한다.

## 완료 판정

다음이 모두 증명될 때만 `status: completed`로 변경한다.

1. 55셀에 `not_explored` 또는 `in_progress`가 없음
2. 모든 `not_supported`와 `not_testable`에 실기기·UI 근거가 있음
3. collection 7개, locked holdout 3개, TVING validation이 분리됨
4. holdout과 TVING 데이터가 승격되지 않음
5. collection 경험이 표준 승격 파이프라인을 거침
6. 최신 B 코드와 N100 배포 커밋이 일치함
7. 공개 Navigation DB가 활성화됨
8. APK 재설치 시 접근성 자동 복원과 실제 바인딩이 검증됨
9. 커버리지 JSON과 문서가 최신 상태임
10. 위험 행동 자동 실행 0건
11. 최종 B 절대 지표와 실패 분석 보고서가 작성됨

완료 전에는 목표를 축소하거나 일부 앱 성공을 전체 완료로 간주하지 않는다.
