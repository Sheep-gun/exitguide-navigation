# ExitGuide Navigation Current Priority

status: verifying
phase: device_validation
updated_at: 2026-08-03T12:51:46+09:00
priority: 기존 ExitGuide Android 기능을 재사용한 Navigation Executor 완성
decision_db_collection: paused
next_action: A100 EXAONE 4.5 콜드 로딩 완료 후 commit 9dd708a APK로 VLM candidate_id allowlist와 최종 실기기 통합 검증을 수행한다.
verification_started_at: 2026-08-03T10:30:41+09:00
verification_completed_at: pending
verified_device: pending
verified_apps: pending
baseline_commit: `a4a47c327468a1670caec6fdcd56be01a0923fc1`
integration_commit: `9dd708ac18c43e6380296f530beb8cf30af7d9fa`
deployed_commit: `9dd708ac18c43e6380296f530beb8cf30af7d9fa`

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
- 최초 실기기 통합 검증: `pending`

## 최초 완료 조건

1. Accessibility 후보가 정상적으로 수집됨
   - status: pending
   - evidence: pending
2. candidate_id 기반 클릭이 실제로 실행됨
   - status: pending
   - evidence: pending
3. 행동 전후 화면 변화가 검증됨
   - status: pending
   - evidence: pending
4. 애매한 화면의 스크린샷이 VLM으로 전달됨
   - status: pending
   - evidence: pending
5. VLM이 현재 화면에 존재하는 candidate_id만 반환함
   - status: pending
   - evidence: pending
6. 실행 실패와 탐색 판단 실패가 별도로 기록됨
   - status: pending
   - evidence: pending
7. 동일 커밋으로 빌드한 APK의 실기기 통합 테스트가 통과함
   - status: pending
   - evidence: pending
   - dangerous_actions_auto_executed: pending

## 현재 통합 구현 테스트 결과

- Navigation API 단위 테스트: passed — integration_commit에서 `apps/api/tests/*.py` 5개
- Android Executor 단위 테스트: passed — `apps/android-executor/app/build/reports/tests/testDebugUnitTest/index.html`
- Android Executor APK 빌드: passed — integration_commit에서 clean `assembleDebug`
- ML Kit OCR 및 AndroidX 빌드: passed — clean Android build
- 실기기 통합 검증: pending
- 위험 행동 자동 실행 0건: pending

## 격리 검증 근거

- isolated_api: `http://100.77.172.25:8101` — `ready=true`, integration_commit 일치
- isolated_code: `/home/kyle/exitguide/runtime/executor-validation-d19a1b5/code`
- isolated_runtime_db: `/home/kyle/exitguide/runtime/executor-validation-d19a1b5/navigation-runtime-v4.sqlite`
- android_device_log: pending
- navigation_api_vlm_log: `/home/kyle/exitguide/runtime/executor-validation-d19a1b5/navigation-api.log` (`device validation pending`)
- a100_vlm_log: `/home/ubuntu/data/exitguide/logs/exaone/server-20260803-124029.log` (`cold loading`)
- device_validation_report: `docs/EXECUTOR_REUSE_DEVICE_VALIDATION_2026-08-03.md` (`pending`)
- apk_path: `apps/android-executor/app/build/outputs/apk/debug/app-debug.apk` — SHA-256 `9904EC6F102ADA2DC12FD30C7110BC49B043ED4C6ACE694B64C8EE876A16F44A`

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
