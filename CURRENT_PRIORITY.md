# ExitGuide Navigation Current Priority

status: completed
phase: device_validation
updated_at: 2026-08-04T03:32:36+09:00
priority: Build a frozen validation-only case DB for public-prior OFF/ON evaluation
decision_db_collection: paused
next_action: Connect the phone and record isolated candidate-complete cases from a validation app (KB Insurance or NH Nonghyup Insurance); do not use collection apps or the locked holdout, and do not promote these validation observations into Decision DB.
verification_started_at: 2026-08-03T10:30:41+09:00
verification_completed_at: 2026-08-03T22:10:05+09:00
verified_device: Samsung SM-S936N, Android 16
verified_apps: YouTube 21.31.524+1561190182; Netflix 9.77.0 build 9 64328+64328; X 12.12.0-release.0+312120000
baseline_commit: `a4a47c327468a1670caec6fdcd56be01a0923fc1`
integration_commit: `c1a8466`
deployed_commit: `c1a8466`

## Promotion pipeline v2

- implementation_commit: `0bdc4efbe8506673328537534cc9020a1192e9a1`
- deployed_code: `/home/kyle/exitguide/runtime/navigation-promotion-pipeline-0bdc4ef`
- generation_id: `generation_92648fdee0389cc62a911ac4`
- generation_dir: `/home/kyle/exitguide/runtime/promotion-pipeline-v2-staging-20260804/generations/generation_92648fdee0389cc62a911ac4`
- n100_unit_test: passed — `/home/kyle/exitguide/runtime/promotion-pipeline-v2-staging-20260804/n100-unit-test.log`
- n100_projection: passed — 88→88 cases, `runtime_db_accessed=false`, `quick_check=ok`, foreign-key errors 0
- operating_decision_db_changed: no
- activation_status: not attempted — validation apps currently have 0 verified cases
- unresolved_provenance: 11 older `uxa_*` real-device rows remain preserved but need their original common episode artifacts

## Public navigation prior integration

- n100_source_commit: `b48af5aa1ef7812596ab67ac731c9398a0fe4238`
- local_integration_branch: `agent/public-prior-integration`
- github_and_n100_deployed_commit: `60184a1b554e51dfcf6e70782e63b3d1619d6a9c`
- n100_service_status: active, ready=true
- operating_decision_db_sha256: `14c73a685ab7c915e9357ba6f99454e738f8f907d0b1abdf77c234825bb4478a`
- public_role: planner advisory context only
- runtime_execution_allowed: false
- canonical_promotion_allowed: false
- task_contract: `navigation-task-knowledge.v1.schema.json`
- task_contract_validation: passed, 570/570 rows and 570 unique task IDs
- irrelevant_task_gate: passed; a service category alone cannot inject a task whose goal text is unrelated
- deployed_membership_cancel_audit: 3 service hints, 0 failure hints, 0 task hints
- n100_warning_log: no entries since deployment
- api_unit_tests: passed, 9/9 files
- fixed_validation_cases: 0
- improvement_claim: not permitted until the frozen validation OFF/ON A/B gate passes
- evidence: `docs/evidence/navigation-public-prior-integration-audit-20260804.md`

## 작업 원칙

- 기존 앱 원본은 읽기 전용으로 감사한다.
- 기존 Runtime DB, Decision DB, Gold, AndroidControl 및 수집 결과는 변경하거나 삭제하지 않는다.
- AndroidControl DB, Gold 경로 재생, 앱별 하드코딩 및 좌표 클릭은 신규 런타임에 이관하지 않는다.
- `status: completed`가 되기 전에는 Decision DB 수집을 재개하지 않는다.
- 최초 통합 검증은 별도 격리 Runtime DB에만 기록하고 실제 학습 경험으로 반입하지 않는다.

## 기능 이관 상태

- 기존 앱 감사 원본: `../exitguide-navigation/apps/mobile/plugins/withExitGuideOverlay.js`
- 기능별 대응표: `docs/EXITGUIDE_EXECUTOR_REUSE_MAPPING.md`
- 이관 연결부 구현: 완료, 실기기 검증 대기
- 최초 실기기 통합 검증: 완료

## 최초 완료 조건

1. Accessibility 후보가 정상적으로 수집됨
   - status: passed
   - evidence: `docs/evidence/android-executor-device-20260803.log` — nodes=82, candidates=22 및 nodes=113, candidates=27
2. candidate_id 기반 클릭이 실제로 실행됨
   - status: passed
   - evidence: `docs/evidence/android-executor-device-20260803.log` — 입력 후보 집합에 존재하는 ID로 3회 클릭 성공
3. 행동 전후 화면 변화가 검증됨
   - status: passed
   - evidence: `docs/evidence/android-executor-device-20260803.log` — 클릭 3회 `screen_changed=true`, 실행 실패는 `false`
4. 애매한 화면의 스크린샷이 VLM으로 전달됨
   - status: passed
   - evidence: `docs/evidence/profile-identifier-masking-and-accessibility-rebind-20260803.md` — 최신 APK 격리 세션에서 `visual_context ready`, `perception=exaone_4_5`, `visualScreenshot=true`
5. VLM이 현재 화면에 존재하는 candidate_id만 반환함
   - status: passed
   - evidence: `docs/evidence/x-vlm-and-state-change-safety-device-20260803.md` — 추천 ID `a11y_df9a5731b862a4339738`가 동일 step의 후보 목록에 존재함; 최신 마스킹 변경은 ID를 보존하며 Android/API 단위 테스트 통과
6. 실행 실패와 탐색 판단 실패가 별도로 기록됨
   - status: passed
   - evidence: 격리 Runtime DB step 3 — planner 성공, executor 실패, 화면 무변화, 연결 정상, `executor_action_not_executed`
7. 동일 커밋으로 빌드한 APK의 실기기 통합 테스트가 통과함
   - status: passed
   - evidence: `docs/evidence/profile-identifier-masking-and-accessibility-rebind-20260803.md`; API와 APK 모두 `36a4abe`, APK SHA-256 `70C14240B60029D2C1FD76A84E66BCA15DFD435C22E4839DDECE82E04026CDB1`
   - dangerous_actions_auto_executed: 0

## 현재 통합 구현 테스트 결과

- Navigation API 단위 테스트: passed — `36a4abe`에서 관련 전체 5개 및 개인정보 저장 경계 회귀 테스트
- Android Executor 단위 테스트: passed — `apps/android-executor/app/build/reports/tests/testDebugUnitTest/index.html`
- Android Executor APK 빌드: passed — integration_commit에서 clean `assembleDebug`
- ML Kit OCR 및 AndroidX 빌드: passed — clean Android build
- 실기기 통합 검증: passed — `docs/EXECUTOR_REUSE_DEVICE_VALIDATION_2026-08-03.md`, `docs/evidence/x-vlm-and-state-change-safety-device-20260803.md`
- 위험 행동 자동 실행 0건: passed

## 격리 검증 근거

- isolated_api: `http://100.77.172.25:8101` — `ready=true`, integration_commit 일치
- isolated_code: `/home/kyle/exitguide/runtime/executor-validation-d19a1b5/code`
- isolated_runtime_db: `/home/kyle/exitguide/runtime/executor-validation-d19a1b5/navigation-runtime-v4.sqlite`
- isolated_safety_replay_db: `/home/kyle/exitguide/runtime/executor-validation-2b6e95f/navigation-runtime-safety.sqlite`
- android_device_log: `docs/evidence/android-executor-device-20260803.log`
- navigation_api_vlm_log: `/home/kyle/exitguide/runtime/executor-validation-d19a1b5/navigation-api.log`
- a100_vlm_log: `/workspace/exitguide-local/logs/exaone/server-20260803-165142.log` (`ready`, N100 영구 터널 경유 HTTP 200, 짧은 추론 1.221초)
- a100_tunnel_service: N100 `exitguide-a100-vlm-tunnel.service` (`active`, 새 A100 port 30000 및 로컬 SSD 모델 연결)
- device_validation_report: `docs/EXECUTOR_REUSE_DEVICE_VALIDATION_2026-08-03.md`
- netflix_tuning_report: `docs/evidence/netflix-membership-cancel-device-tuning-20260803.md`
- x_vlm_safety_report: `docs/evidence/x-vlm-and-state-change-safety-device-20260803.md`
- privacy_revalidation_report: `docs/evidence/profile-identifier-masking-and-accessibility-rebind-20260803.md`
- apk_path: `apps/android-executor/app/build/outputs/apk/debug/app-debug.apk` — SHA-256 `70C14240B60029D2C1FD76A84E66BCA15DFD435C22E4839DDECE82E04026CDB1`

## 완료 및 재개 규칙

- 7개 조건이 모두 `passed`이고 `integration_commit`, APK 빌드 커밋, `deployed_commit`가 일치할 때만 `status: completed`로 변경한다.
- 하나라도 `pending` 또는 `failed`이면 `status: verifying`을 유지한다.
- 외부 연결 또는 기기 문제로 검증 자체가 불가능할 때만 `status: blocked`로 변경하고 원인을 기록한다.
- `completed`: 완료 조건을 반복 시험하지 않고 Decision DB 수집을 계속한다.
- `verifying`: DB 수집을 금지하고 `next_action`부터 계속한다.
- `blocked`: 기록된 차단 원인을 먼저 해결한다.

다음 경우에만 영향을 받는 완료 조건을 다시 시험한다.

- AccessibilityService 또는 후보 추출 코드 변경
- Executor 또는 화면 변화 관찰 코드 변경
- OCR/VLM 연동 코드 변경
- APK 구현 교체
- 완료 기록과 실제 APK/API 배포 커밋 불일치
- 실기기 기능 회귀 발견

컨텍스트 압축, 새 세션, 문서 수정, DB 데이터 추가는 재시험 사유가 아니다.
