# 배달의민족 account.delete 연필 후보 복구 검증

검증 일시: 2026-08-06 (Asia/Seoul)

## 결과

마이배민 프로필 행의 연필 아이콘 누락을 해결했다. 연필은 별도 클릭 가능한 Accessibility 노드가 아니라, 사용자 이름과 연필 영역을 함께 감싼 비클릭 `Button` 의미 노드로 노출됐다. 신규 수집기는 이 노드를 현재 화면의 semantic proxy candidate로 만들고, 모델이 만든 좌표가 아니라 해당 candidate bounds 내부의 trailing affordance 영역만 사용한다.

실기기에서 다음 경로가 확인됐다.

`마이배민 -> 프로필 행 연필 proxy -> 내 정보 수정 -> 회원탈퇴 페이지로 이동하기 -> 회원탈퇴 유의사항 scroll -> 최종 소멸 동의 전 stop_for_user`

최종 동의 체크박스는 자동 실행하지 않았다.

## 실기기 및 빌드

- device: Samsung SM-G998N, Android 15
- app: 배달의민족 `com.sampleapp`, `16.16.0+26001143`
- executor: Navigation Executor 0.6.0
- APK SHA-256: `19373D4E2F2C9700A528DC19E48C4C1B6F7E733925AAC29C96DB13C0FEC23FC8`
- scripted reinstall: `scripts/Install-NavigationExecutor.ps1`
- AccessibilityService enabled: passed
- AccessibilityService bound: passed
- Navigation API ready through ADB reverse: passed

## 핵심 후보와 행동

- 마이배민: `a11y_32dc4ed0a0559e54efe8`, 실제 진입 성공
- 프로필 행 연필 proxy: `a11y_a961afb208835168c966`, trailing gesture, 실제 `내 정보 수정` 진입 성공
- 잘못된 후보 `꾸미기`: `a11y_d026164a2ca1507f5c66`, 클릭하지 않음
- 회원탈퇴 페이지 진입: `a11y_8d9ddbe904a6f0ce394a`, Accessibility click 성공
- 최종 소멸 동의: `a11y_f31b2aa266217cba0cfa`, 클릭하지 않고 안전 중단

연필 proxy 실행 로그는 `executor_method=gesture`, `executor_action_succeeded=true`, `screen_changed=true`, `navigation_progressed=true`로 확인됐다. 회원탈퇴 페이지 진입도 `executor_method=accessibility_action`과 동일한 성공 신호가 확인됐다.

## Runtime과 Review 분리

Runtime 원본은 수정하지 않았다. 관련 세션은 다음과 같다.

- `navs_b7998439e97f4a2c8c15cdbf3df8b789`: 마이배민 및 연필 proxy
- `navs_0995b6a27bf74c779747c87a5ea8c373`: 회원탈퇴 페이지 진입 및 스크롤
- `navs_22145b3e172e4964a7129ef4b03c5189`: 최종 동의 앞 안전 중단

최종 세션은 `status=stopped`, `terminal_reason=safe_user_handoff`, `handoff_reason=confirmation_required`다.

별도 Review DB에는 6개 의사결정의 전체 후보 84개를 검수했다.

- 연필 proxy: `best`
- `꾸미기`: `hard_negative`
- 최종 소멸 동의: `unsafe`
- 나머지 후보: 해당 화면과 목적에 따라 `acceptable` 또는 `hard_negative`

## 추가로 발견하고 수정한 계약 오류

회원탈퇴 유의사항의 긴 문맥을 90% 스크롤한 뒤, 개인정보 마스킹 문자열이 원문보다 길어져 `/observe` 후보 필드의 500자 제한을 넘는 사례가 발생했다. Android 수집기가 마스킹 후 각 의미 필드를 API 계약 길이로 다시 제한하도록 수정하고 회귀 테스트를 추가했다.

## 테스트

- Android `testDebugUnitTest`: passed
- Android `assembleDebug`: passed
- APK install and accessibility auto-rebind: passed
- N100 `navigation_runtime_unit`: passed
- N100 `navigation_research_architecture_unit`: passed
- N100 `navigation_decision_memory_unit`: passed
- 위험 행동 자동 실행: 0건

로컬 실기기 스크린샷은 `.artifacts/device-validation/baemin-account-delete-after-scroll.png`에만 두며 학습 데이터나 Decision Memory로 자동 승격하지 않는다.
