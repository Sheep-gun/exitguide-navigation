# Android Executor v1

`apps/android-executor`는 Navigation API가 승인한 행동을 실기기에서 실행하고, 행동 전후 화면과 전체 후보를 다시 API에 보내는 수집기다. 앱별 Gold 경로를 재생하지 않으며 임의 좌표를 만들지 않는다.

## 한 단계의 실제 흐름

1. Accessibility tree에서 `visible + enabled + clickable` 후보를 전부 수집한다.
2. 각 후보에 텍스트, 아이콘 설명, 주변 문구, 부모 문맥, 화면 위치와 안정적인 `candidate_id`를 붙인다.
3. 가능하면 화면 스크린샷도 EXAONE 4.5용으로 `/v1/navigation/decide`에 전달한다.
4. API는 `click(candidate_id)`, `scroll`, `back`, `wait_and_observe`, `stop_for_user` 중 하나만 반환한다.
5. 실행기는 클릭 직전에 현재 tree에서 같은 후보를 다시 찾고 위험도를 다시 검사한다.
6. 행동 후 새 화면과 전체 후보를 `/v1/navigation/observe`로 보낸다.
7. N100 runtime DB에는 before/after 화면, 전체 후보, 점수, 선택 행동, 연결 상태, 결과, 실패와 복구 힌트가 저장된다.
8. 목적지 또는 위험한 최종 행동 앞에서는 자동화를 끝내고 사용자에게 넘긴다.

연결 오류는 UI 탐색 실패로 바꾸지 않는다. 같은 HTTP 요청은 최대 세 번 재전송하며, 서버의 request cache가 같은 `request_id`를 멱등 처리한다.

## 이중 안전 장치

- 서버 Python gate: 현재 화면 후보 ID가 아닌 클릭, 금지 후보, 고위험 후보를 `stop_for_user`로 바꾼다.
- Android local gate: 서버 응답과 무관하게 좌표 클릭·텍스트 입력을 지원하지 않고, switch/checkbox/radio/editable 및 결제·가입·탈퇴·해지 확정 문구를 다시 차단한다.
- 최대 15개 행동 또는 10분 후 자동 중지한다.
- 탐색이 활성화된 동안 Android wake-lock으로 화면 꺼짐을 막고 종료 시 해제한다. 화면 유지용 임의 좌표 터치는 보내지 않는다.
- 다른 앱으로 이동, 로그인 요구, 네트워크 오류, 실행 거절을 별도 signal로 관찰한다.

## 빌드

```powershell
$env:ANDROID_HOME='C:\Users\YangGeon\ExitGuideAndroidSdk'
$env:ANDROID_SDK_ROOT=$env:ANDROID_HOME
cd apps\android-executor
.\gradlew.bat testDebugUnitTest assembleDebug --no-daemon
```

APK는 `apps/android-executor/app/build/outputs/apk/debug/app-debug.apk`에 생성된다. 기본 API 주소는 `http://100.77.172.25:8100`이며 앱 화면에서 변경할 수 있다.

## 실기기 사용

1. 휴대폰이 N100과 같은 Tailscale 네트워크에서 `100.77.172.25:8100`에 접근 가능한지 확인한다.
2. APK를 설치하고 Android 설정에서 `ExitGuide 후보 기반 탐색` 접근성 서비스를 활성화한다.
3. 평가할 앱의 시작 화면을 사용자가 직접 연다.
4. Executor에 목적을 입력하고 `안전 탐색 시작`을 누른다.
5. 최종 확정 버튼 앞에서 멈추면 사용자가 직접 확인한다.
6. `GET /v1/navigation/sessions/{session_id}/episode`로 수집된 후보·행동·결과를 검사한다.

이 빌드는 화면 탐색 경험을 수집할 준비가 된 상태다. 앱별 실제 성공률 주장은 앱 분리 실기기 평가가 끝난 뒤에만 확정한다.
