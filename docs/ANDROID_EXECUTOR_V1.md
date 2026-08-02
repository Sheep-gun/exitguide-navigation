# Android Executor v1

`apps/android-executor`는 Navigation API가 승인한 행동을 실제 Android에서 수행하는 최소
네이티브 실행기다. 기존 Expo 앱이나 Gold 재생 코드를 복원하지 않고 별도 프로젝트로
구성했다.

## 실행 경계

- AccessibilityService가 현재 창에서 `visible + enabled + clickable` 노드만 열거한다.
- 후보 ID는 semantic fingerprint와 accessibility tree path의 SHA-256으로 만든다.
- API 요청과 응답에는 좌표 필드가 없다.
- `dispatchGesture`, 임의 tap 좌표, 텍스트 입력은 구현하지 않았다.
- 클릭 직전에 현재 tree에서 같은 fingerprint의 노드를 다시 찾고 위험도를 재검사한다.
- switch, checkbox, radio, editable node와 탈퇴·해지·결제·개인정보 제출 최종 문구는 차단한다.
- scroll은 실제 `isScrollable()` 노드의 Accessibility action만 사용한다.
- 연결 오류는 `/observe`의 UI 탐색 실패로 위조하지 않는다.
- 한 세션은 최대 16행동이며 목적지/위험 최종행동 앞에서 `stop_for_user()`로 끝난다.

## 빌드

```powershell
$env:ANDROID_HOME='C:\Users\YangGeon\ExitGuideAndroidSdk'
$env:ANDROID_SDK_ROOT=$env:ANDROID_HOME
cd apps\android-executor
.\gradlew.bat testDebugUnitTest assembleDebug --no-daemon
```

로컬 APK 출력은 `apps/android-executor/app/build/outputs/apk/debug/app-debug.apk`다. GitHub
Actions의 `Android Navigation Executor` workflow도 동일 APK를 `navigation-executor-debug`
artifact로 올린다. APK 파일과 API 비밀키는 Git에 커밋하지 않는다.

## 실기기 전 준비

1. N100의 Navigation API를 휴대폰에서 접근 가능한 주소로 제공한다.
2. 앱의 Navigation API 주소와 자연어 목적을 입력한다.
3. Android 설정에서 ExitGuide 후보 기반 탐색 접근성 서비스를 활성화한다.
4. 위험한 최종 행동은 앱이 멈춘 뒤 사용자가 직접 수행한다.

현재는 오프라인 리플레이·합성 화면·로컬 APK 빌드까지 통과했다. N100↔A100의 지속형
서비스 간 터널이 아직 없어 실기기 검증은 시작하지 않았다.
