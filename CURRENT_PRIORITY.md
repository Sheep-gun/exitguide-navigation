# ExitGuide Navigation Current Priority

status: verifying
phase: implementation
updated_at: 2026-08-03T21:15:55+09:00
priority: 계정·프로필 문맥의 평문 식별자 마스킹 누락 수정
decision_db_collection: paused
next_action: 기존 Runtime 기록은 보존하고 Android Executor와 Runtime 저장 경계에 문맥 기반 계정 식별자 마스킹을 추가한 뒤 개인정보 관련 영향 조건만 재검증한다.
verification_started_at: 2026-08-03T10:30:41+09:00
verification_completed_at: 2026-08-03T20:35:50+09:00
verified_device: Samsung SM-S936N, Android 16
verified_apps: YouTube 21.31.524+1561190182; Netflix 9.77.0 build 9 64328+64328; X 12.12.0-release.0+312120000
baseline_commit: `a4a47c327468a1670caec6fdcd56be01a0923fc1`
integration_commit: `3c49a52`
deployed_commit: `3c49a52`

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
   - evidence: `docs/evidence/x-vlm-and-state-change-safety-device-20260803.md` — X step 0의 서버 요청 후 step 1에서 `perception_provider=exaone_4_5`, `visual_reobserve_required=false`
5. VLM이 현재 화면에 존재하는 candidate_id만 반환함
   - status: passed
   - evidence: `docs/evidence/x-vlm-and-state-change-safety-device-20260803.md` — 추천 ID `a11y_df9a5731b862a4339738`가 동일 step의 후보 목록에 존재함
6. 실행 실패와 탐색 판단 실패가 별도로 기록됨
   - status: passed
   - evidence: 격리 Runtime DB step 3 — planner 성공, executor 실패, 화면 무변화, 연결 정상, `executor_action_not_executed`
7. 동일 커밋으로 빌드한 APK의 실기기 통합 테스트가 통과함
   - status: passed
   - evidence: `docs/evidence/x-vlm-and-state-change-safety-device-20260803.md`, `docs/evidence/netflix-membership-cancel-device-tuning-20260803.md`; API와 APK 모두 `3c49a52`, APK SHA-256 `45BE8C24E42AF3AB2E778E0BFBC1144CE6C938FAFF5A078586F0FD8925F89FFC`
   - dangerous_actions_auto_executed: 0

## 현재 통합 구현 테스트 결과

- Navigation API 단위 테스트: passed — integration_commit에서 `apps/api/tests/*.py` 5개
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
- apk_path: `apps/android-executor/app/build/outputs/apk/debug/app-debug.apk` — SHA-256 `45BE8C24E42AF3AB2E778E0BFBC1144CE6C938FAFF5A078586F0FD8925F89FFC`

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
