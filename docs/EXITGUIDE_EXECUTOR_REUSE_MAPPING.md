# 기존 ExitGuide → Navigation Executor 기능 이관 대응표

이 문서는 기존 앱을 읽기 전용으로 감사한 결과와 신규 Executor의 실제 연결 상태를 기록한다.

- 기존 원본: `../exitguide-navigation/apps/mobile/plugins/withExitGuideOverlay.js`
- 신규 Android 앱: `apps/android-executor`
- Navigation API: `apps/api`
- 감사 기준 커밋: `a4a47c327468a1670caec6fdcd56be01a0923fc1`
- 판정: `reused`는 안전 로직 이관 완료, `adapted`는 패키지/API 차이만 최소 수정, `partial`은 연결부 보완 필요, `excluded`는 의도적으로 이관 금지

기존 구현은 Expo config plugin 안에서 Java 소스를 생성하는 구조라 Java 클래스를 바이너리 모듈로 직접 import할 수 없다. 따라서 검증된 로직을 신규 앱의 작은 전용 클래스에 옮기고, 금지된 좌표·Gold·AndroidControl 경로는 제거하는 방식으로 이관한다.

## 기능별 대응

| 기능 | 기존 구현 위치 | 신규 구현 위치 | 상태 | 이관 판단 및 남은 연결부 |
|---|---|---|---|---|
| AccessibilityService 등록·설정 | `withExitGuideOverlay.js:50-64`, `:1472-1481` | `app/src/main/AndroidManifest.xml`, `res/xml/accessibility_service_config.xml` | adapted | 노드 조회·스크린샷 권한을 신규 단일 앱 서비스에 연결. 실기기 권한 확인 필요 |
| 활성 앱 이벤트 필터링 | `onAccessibilityEvent` `:1644`, `isRelevantAccessibilityEventPackage` `:2644-2664` | `ExitGuideAccessibilityService.onAccessibilityEvent` | adapted | 이벤트 패키지와 현재 활성 root 패키지 일치를 재검사하고 자체 앱·System UI 이벤트를 제외 |
| 전체 Accessibility 노드 수집 | `appendNode` `:3020-3103` | `AccessibilityScreenReader.read/traverse`, API `AccessibilityNodeSummary` | adapted | 최대 500개 visible/on-screen 노드를 비좌표 의미 요약으로 직렬화하고 후보 ID를 node ID에 grounding |
| 클릭 가능한 전체 후보 추출 | `indexClickableElements` `:3183-3223` | `AccessibilityScreenReader.addCandidate` | adapted | 보이는·활성·클릭 가능 노드만 후보화하고 최대 개수를 제한함 |
| 안정적 candidate_id | `stableNodeId` `:3105-3115` | `AccessibilityScreenReader.nodeFingerprint` | adapted | view id·class·의미·트리 경로를 해시함. 화면 간 재탐색 시 fingerprint를 재검사함 |
| 텍스트·아이콘·위치·주변 문구 | `appendNode` `:3052-3088` | `AccessibilityScreenReader.addCandidate`, `siblingText`, `positionBucket` | reused | 절대 좌표는 기기 내부 binding에만 유지하고 API에는 의미적 위치만 전달 |
| 부모·자식 관계 | `appendNode(parentId)` `:3020-3101` | `node_id/parent_id/child_ids`, `parent_semantics`, `child_semantics` | adapted | 전체 노드 관계와 후보 주변 의미를 함께 전달하고 API에서 참조 무결성을 검사 |
| Accessibility node 클릭 | `performExplorationClick` `:2769-2809` | `ExitGuideAccessibilityService.clickCandidate` | reused | 클릭 직전 동일 node fingerprint·가시성·활성·위험도를 재검사한 뒤 `ACTION_CLICK`만 실행 |
| 좌표 제스처 클릭 | `dispatchTapAtBounds` `:2812-2829` | 없음 | excluded | 임의 좌표 및 bounds 중심 클릭은 신규 런타임에서 금지 |
| Accessibility 스크린샷 | `captureOcrAndSubmit` `:1925-2001` | `ExitGuideAccessibilityService.prepareVisualContext` | adapted | `takeScreenshot`과 HardwareBuffer→software Bitmap 흐름을 이관. 모호한 화면에서만 사용 |
| 한국어 OCR | ML Kit 초기화 `:1606`, `:1628-1631`; 실행 `:1960` | `VisualScreenAugmenter` | adapted | 같은 ML Kit Korean recognizer 사용. OCR은 기존 Accessibility 후보 의미만 보완 |
| OCR 좌표 후보 생성 | `appendOcrElements` `:2182-2225` | 없음 | excluded | OCR만으로 새 candidate_id나 좌표 클릭 대상을 만들지 않음 |
| 개인정보 마스킹 | `buildPrivacyMaskedVisualContext` `:2012-2068` | `VisualScreenAugmenter.buildMaskedOverlayDataUrl`, `redactSnapshotInPlace` | adapted | 이미지와 전송 후보 의미를 기기에서 마스킹. 원본 이미지는 파일로 저장하지 않음 |
| 선택적 시각 문맥 | `needsVisualContext` `:2071-2089` | `AccessibilityScreenReader.needsVisualReasoning`, API `AndroidWorldResearchPolicy.perceive` | adapted | 이름 없는 후보·점수 근접·WebView/Canvas·팝업·무변화·DB–Solar 충돌에서 클릭을 보류하고 VLM 재관찰 |
| EXAONE 4.5 VLM 요청 | 기존 앱은 마스킹된 `visualContext`를 서버 요청에 포함 `:2107-2174` | Executor `/decide` 요청 + API `Exaone45VisionClient.perceive` | adapted | 기기는 VLM을 직접 호출하지 않고 전체 후보와 이미지를 Navigation API에 전달 |
| VLM candidate_id 제한 | 기존 서버 응답의 element id 사용 | API `Exaone45VisionClient.perceive` allowlist + Python 안전 게이트 | reused | VLM 주석 중 현재 후보 집합 밖의 ID를 폐기. 실제 로그 검증 필요 |
| candidate_id 이미지 오버레이 | 기존 compact 상태 overlay만 존재; 이미지 ID overlay 없음 | `VisualScreenAugmenter.buildMaskedOverlayDataUrl` | adapted | 신규 요구 연결부. 현재 후보 bounds와 기존 candidate_id만 이미지에 표시 |
| 화면 안정화·중복 이벤트 억제 | bounded settle `:1826-1833`; tree signature 억제 `:2121-2137` | `observeWhenSettled`, `EpisodeGenerationGuard` | adapted | UI 이벤트 quiet window 후 `/observe`; 오래된 비동기 callback은 generation으로 폐기 |
| 앱 전환·외부 이동 관찰 | 활성 패키지 검사 `:2644-2664` | 활성 root 필터, `ObservationSignalDetector`, 전후 `appPackage` 비교 | adapted | 잘못된 패키지 이벤트를 제외하고 실제 전후 패키지 변화만 external app으로 기록 |
| 앱 버전·locale | 기존 요청의 package/환경 문맥 | Executor `packageVersion`, API Runtime session | adapted | 패키지 versionName/longVersionCode와 locale을 Runtime session에 기록; v3→v4 마이그레이션 지원 |
| 권한 상태 | overlay/accessibility 권한 검사·manifest | `MainActivity`, Manifest, accessibility config | adapted | 접근성 권한 UI 및 API 상태 확인 존재. 실기기 검증 필요 |
| 화면 켜짐 유지 | 기존 Accessibility 코드에 전용 wake-lock 없음 | `ExitGuideAccessibilityService.holdScreenAwake` | adapted | 신규 Executor 요구에 따라 OS WakeLock만 사용. keep-alive 좌표 터치는 없음 |
| 행동 전후 검증 | 기존 tree signature와 후속 분석 | Executor `/decide` 실행 결과 + `/observe`; API `verify_transition` | adapted | planner 판단, executor 실행, screen change, progress, connection을 별도 필드·테이블로 기록 |
| Gold 기록·재생 | 기존 record/explore 분기 및 transition 기록 | 없음 | excluded | 기존 자료는 비교용으로만 보존하고 신규 런타임에서 재생하지 않음 |
| AndroidControl·앱별 경로 | 기존 데이터 경로 | 없음 | excluded | 신규 Executor/API가 조회하지 않음 |

## 구현 완료·검증 대기 연결부

1. 전체 노드 비좌표 요약과 명시적 부모·자식 ID 계약: 구현 및 단위 테스트 완료, 실기기 대기.
2. 활성 root 패키지 이벤트 필터: 구현 및 빌드 완료, 실기기 대기.
3. 점수 근접·DB–Solar 충돌 VLM 재관찰: 구현 및 단위 테스트 완료, 실제 EXAONE 요청 대기.
4. planner/executor/screen/progress/connection 결과 분리: 구현 및 단위 테스트 완료, 격리 Runtime 검증 대기.
5. candidate_id node 클릭, OCR, 마스킹 overlay APK: clean 빌드 완료, 동일 구현 커밋 고정 후 실기기 대기.

## 이관 금지 확인

- `dispatchGesture` 또는 bounds 중심 좌표 클릭: 이관하지 않음
- OCR-only candidate 생성: 이관하지 않음
- Gold 경로 자동 재생: 이관하지 않음
- AndroidControl DB 조회: 이관하지 않음
- 앱 패키지별 정답 경로 분기: 이관하지 않음
