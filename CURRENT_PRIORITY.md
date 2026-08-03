# ExitGuide Navigation Current Priority

status: verifying
phase: device_validation
updated_at: 2026-08-04T09:25:00+09:00
priority: B 고정 아키텍처로 11개 앱 × 5개 목표의 실기기 커버리지 55셀 완성
decision_db_collection: paused
next_action: 변경을 커밋·배포한 뒤 7/3/1 coverage split을 사용하는 보존형 Runtime을 준비하고 첫 collection 미완료 셀 검증을 시작한다.
verification_started_at: 2026-08-04T08:45:00+09:00
verification_completed_at: pending
verified_device: Samsung SM-S936N, Android 16
verified_apps: YouTube 21.31.524+1561190182; Netflix 9.77.0 build 9 64328+64328; X 12.12.0-release.0+312120000; TVING 26.31.02+20263102
baseline_commit: `a4a47c327468a1670caec6fdcd56be01a0923fc1`
integration_commit: `c137e68a9bdd266bacfe3adc3b83fcd869133437`
deployed_commit: `c137e68a9bdd266bacfe3adc3b83fcd869133437`

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
- current_coverage_scope: 11/11 앱, 55셀 계약 검증 통과; 최종 상태 4셀, 미완료 51셀

holdout 3개와 TVING 경험은 Decision DB 또는 App Knowledge로 승격하지 않는다.

## N100 운영 상태 — 2026-08-04 확인

- service: `exitguide-navigation-api.service`, active
- endpoint: `http://100.77.172.25:8100`
- ready: true
- code: `/home/kyle/exitguide/runtime/navigation-api-code-c137e68`
- deployed_git_head: `c137e68a9bdd266bacfe3adc3b83fcd869133437`
- public_prior.enabled: true
- public service episodes/transitions: 2,047 / 27,343
- public failure transitions: 2,737
- public task records: 570
- Decision DB: read-only patched immutable clone
- Runtime DB: sessions 113, decisions 393, observations 355
- production split SHA-256: `9fa006adc74fc117c180ba051fd50e355fcb80ba6e970dd1e5b4a2fe43141142`
- production split counts: collection 8, validation 2, locked_holdout 3
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
- Accessibility nodes/candidates: 13/5
- B Navigation API ready/public prior: true/true
- Runtime sessions/decisions before and after diagnostic: 113/393, 변화 없음
- APK SHA-256: `0E7D31F62E3B6B58EF08AC756FF998C8D17F2C32DD71750D0B672257FE23FC9D`
- evidence: `docs/evidence/navigation-executor-auto-rebind-20260804.md`

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
