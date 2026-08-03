# Navigation Executor APK 자동 접근성 복원 검증 — 2026-08-04

## 결론

`scripts/Install-NavigationExecutor.ps1`을 인자 없이 실행해 APK를 `adb install -r`로
교체한 뒤 사용자 설정 화면 조작 없이 ExitGuide AccessibilityService를 복원했다.
설정 문자열뿐 아니라 `dumpsys accessibility`의 bound-service 레코드를 확인했고,
진단 전용 비실행 경로로 Accessibility 노드 13개, candidate_id 후보 5개와 B 운영
Navigation API 연결을 검증했다.

## 검증 환경

- 기기: Samsung SM-S936N, Android 16
- serial: `R3CY204GDVE`
- APK: `apps/android-executor/app/build/outputs/apk/debug/app-debug.apk`
- APK SHA-256: `0E7D31F62E3B6B58EF08AC756FF998C8D17F2C32DD71750D0B672257FE23FC9D`
- APK 크기: 52,569,551 bytes
- 실행 명령: `powershell -ExecutionPolicy Bypass -File .\scripts\Install-NavigationExecutor.ps1`
- Navigation API: N100 운영 8100, B 고정, `public_prior.enabled=true`

## 실제 결과

스크립트 JSON 결과:

- `accessibility_enabled=true`
- `accessibility_bound=true`
- `preserved_service_count=2`
- `node_collection_ready=true`
- `candidate_id_generation_ready=true`
- `navigation_api_ready=true`
- `nodes=13`
- `candidates=5`
- diagnostic request ID: `45094ee47a414837a965e5ff0d4c6e32`

기기 로그:

- `diagnostic_snapshot ... package=com.exitguide.navigation.executor nodes=13 candidates=5`
- `diagnostic_api ... ready=true public_prior_enabled=true`

진단 receiver는 먼저 기존 탐색 active 상태를 false로 만들고, 화면 구조의 개수와 API
GET 상태만 확인한다. candidate를 클릭하거나 Navigation `/decide`·`/observe`를 호출하지
않는다. 검증 전후 운영 Runtime은 sessions 113, decisions 393으로 변하지 않았다.

## 자동 복원 범위

1. ADB 자동 탐색 및 단일 authorized 기기 확인
2. `adb install -r`로 앱 데이터·기존 설정 보존
3. 다른 접근성 서비스 목록 보존
4. ExitGuide service component 중복 없이 추가
5. `accessibility_enabled=1` 설정
6. bound-service polling
7. 미바인딩 시 ExitGuide component만 토글하고 자동 재시도
8. 실제 Accessibility 노드와 candidate_id 후보 생성 확인
9. 기기에서 B 운영 Navigation API `ready=true` 확인

진단은 임의 좌표, Gold 재생, AndroidControl DB 또는 위험 행동을 사용하지 않았다.
