# 팀원용 Navigation Executor 설치·실행·병렬 수집 안내

## 배포 상태

- N100 최초 확인 시 APK 파일은 없었다.
- 이 배포본은 Android Executor 구현 커밋 `07280a813ded8bcc77a34fe6b748e7d6a541abec`에서 빌드했다.
- APK SHA-256은 `C9B64BF2D724533265B28BEBEE6E7A6B42078D0B797AB2C3C338AAF3E8D4A699`이다.
- Android 단위 테스트와 APK 빌드는 통과했다.
- 90% 화면 스크롤과 ADB 연결 해제 시 자동 일시정지가 포함돼 있다.
- 이 정확한 APK의 실기기 재검증은 양건 기기 연결 해제로 아직 `pending`이다. 팀원 기기 검증 결과도 학습 성공 데이터로 자동 승격하지 않는다.

N100 배포 위치:

```text
/srv/exitguide/releases/navigation-executor/07280a8/
```

## 구성

```text
navigation-executor-07280a8-team.zip
├─ navigation-executor-debug.apk
├─ README.ko.md
├─ SHA256SUMS.txt
├─ config/
│  ├─ navigation_coverage_split_v1.json
│  └─ navigation_goal_coverage_v1.json
└─ scripts/
   ├─ Setup-TeamNavigationExecutor.ps1
   ├─ Install-NavigationExecutor.ps1
   ├─ Start-NavigationExecutorGoal.ps1
   ├─ Stop-NavigationExecutorGoal.ps1
   └─ Monitor-NavigationExecutorDevice.ps1
```

개인 SSH 키, Solar 키, A100 키와 N100 비밀 설정은 묶음에 포함하지 않는다. 팀원은 서버에 이미 등록된 자기 개인키만 사용한다.

## 1. 준비물

- Windows 10/11 PowerShell
- Tailscale에서 N100 `100.77.172.25` 접근 가능
- N100 공용 계정에 등록된 본인의 SSH 개인키
- Android platform-tools의 `adb.exe`
- USB 디버깅을 허용한 Android 휴대폰 1대
- 수집할 앱이 휴대폰에 설치되고 필요한 계정 상태가 준비돼 있어야 함

`tailscale set --ssh`는 실행하지 않는다. N100은 일반 OpenSSH와 기존 공개키 인증을 사용한다.

## 2. N100에서 내려받기

PowerShell에서 명시적으로 Windows OpenSSH 실행 파일을 사용한다. `<개인키경로>`만 자신의 값으로 바꾼다.

```powershell
& "$env:WINDIR\System32\OpenSSH\scp.exe" `
  -i <개인키경로> `
  exitguide@100.77.172.25:/srv/exitguide/releases/navigation-executor/07280a8/navigation-executor-07280a8-team.zip `
  .

Expand-Archive .\navigation-executor-07280a8-team.zip -DestinationPath .\navigation-executor-07280a8
Set-Location .\navigation-executor-07280a8
Get-FileHash -Algorithm SHA256 .\navigation-executor-debug.apk
```

출력된 APK 해시는 반드시 다음과 같아야 한다.

```text
C9B64BF2D724533265B28BEBEE6E7A6B42078D0B797AB2C3C338AAF3E8D4A699
```

## 3. 연결·설치·접근성 복원

휴대폰을 USB로 연결하고 USB 디버깅을 허용한 다음 실행한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Setup-TeamNavigationExecutor.ps1 `
  -SshKeyPath <개인키경로>
```

ADB가 PATH에 없으면 다음처럼 지정한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Setup-TeamNavigationExecutor.ps1 `
  -SshKeyPath <개인키경로> `
  -AdbPath C:\Android\platform-tools\adb.exe
```

이 스크립트는 다음 작업을 수행한다.

1. 팀원 PC의 `127.0.0.1:18104`에서 N100 `100.77.172.25:8100`으로 숨김 SSH 터널을 연다.
2. 휴대폰의 `127.0.0.1:8100`을 팀원 PC의 `18104`로 `adb reverse`한다.
3. `adb install -r`로 APK를 설치해 앱 데이터와 기존 설정을 보존한다.
4. 기존 접근성 서비스 목록을 보존하면서 ExitGuide 서비스만 추가·복원한다.
5. `dumpsys accessibility`에서 실제 바인딩을 확인한다.
6. Accessibility 노드, candidate_id 후보, B 고정 Navigation API 연결을 진단한다.
7. N100 split manifest가 고정값 `a26cb574...41142`인지 검사한다.

성공 출력에는 최소한 다음 값이 있어야 한다.

```text
status: ready
architecture: B_fixed
n100_api_ready: true
public_prior_enabled: true
accessibility_bound: true
nodes: 1 이상
candidates: 1 이상
navigation_api_ready: true
```

재설치 없이 연결만 복원하려면 `-SkipInstall`을 붙인다.

## 4. 목표 실행과 중지

예시:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Start-NavigationExecutorGoal.ps1 `
  -AppPackage com.netflix.mediaclient `
  -Goal "멤버십 가입 메뉴까지 이동"
```

중지:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Stop-NavigationExecutorGoal.ps1
```

Executor가 허용하는 행동은 `click(candidate_id)`, `scroll(direction)`, `back()`, `wait_and_observe()`, `stop_for_user()`뿐이다. 임의 좌표 클릭은 사용하지 않는다.

회원탈퇴 확정, 멤버십 해지 확정, 결제·구독 확정, 개인정보 제출, 로그인 정보 입력, 약관 최종 동의와 외부 전송 직전에는 반드시 `stop_for_user()`로 끝나야 한다.

## 5. 병렬 수집 규칙

N100 운영 API는 단일 Uvicorn 프로세스이며 Runtime SQLite 쓰기는 프로세스 내부 잠금과 SQLite `busy_timeout=10초`로 직렬화된다. 여러 팀원이 서로 다른 세션을 동시에 보낼 수는 있지만, 현재 Runtime 스키마에는 별도 `collector_id` 열이 없다. 따라서 세션 ID와 작업 할당 기록이 수집자 추적의 기준이다.

반드시 다음 규칙을 지킨다.

1. 시작 전에 앱·`goal_id` 한 셀을 팀 채널에서 선점한다. 같은 셀을 동시에 수집하지 않는다.
2. 실행 후 API가 반환한 `session_id`, 앱 버전, 기기 모델, 시작·종료 시각과 결과를 작업 기록에 남긴다.
3. 연결 오류는 탐색 실패, 후보 없음, `not_supported`, `not_testable`로 기록하지 않는다.
4. ADB가 끊기면 해당 세션은 자동 일시정지되며 자동 재개되지 않는다. 다시 연결한 뒤 설치 스크립트로 바인딩을 확인하고 새 세션으로 명시적으로 시작한다.
5. Runtime DB에서 Decision DB로 직접 삽입하지 않는다.
6. 검증된 collection 경험만 다음 표준 경로의 승격 후보가 될 수 있다.

```text
Runtime DB
→ interaction-episode.v1
→ knowledge-promotion.v1
→ 반복 검증·리플레이·승인
→ App Knowledge generation
→ Decision DB projection
```

## 6. 데이터 분리

### collection: 수집 및 검증 후 승격 후보 가능

- YouTube: `com.google.android.youtube`
- Netflix: `com.netflix.mediaclient`
- 제주항공: `com.parksmt.jejuair.android16`
- X: `com.twitter.android`
- 쿠팡: `com.coupang.mobile`
- 배달의민족: 현재 manifest의 package 값을 사용
- NH농협손해보험: `ni.mh.android.launcher`

### locked_holdout: 수집 동결 전 접근·튜닝·승격 금지

- Instagram: `com.instagram.android`
- 포스타입: `com.postype.play`
- ChatGPT: `com.openai.chatgpt`

### validation: 평가만 가능, 승격 금지

- TVING: `net.cj.cjhv.gs.tving`

팀원은 번들 안의 `config/navigation_coverage_split_v1.json`을 단일 분리 기준으로 사용한다. locked holdout은 collection 완료·동결 지시가 있기 전에는 실행하지 않는다.

## 7. 결과 보고 형식

```text
collector: 팀원 식별명
device: 제조사/모델/Android 버전
app_package: 패키지명
app_version: 버전
goal_id: account.signup | account.delete | membership.join | membership.change | membership.cancel
split: collection | validation | locked_holdout
session_id: navs_...
started_at: ISO-8601
finished_at: ISO-8601
terminal_status: destination_reached | safe_boundary_reached | not_supported | not_testable | paused
connection_error: true | false
dangerous_action_auto_executed: false
notes: 실패·복구·팝업·WebView·로그인 요구 등
```

## 8. 장애 판단

- `ssh`가 Windows 앱 선택 창으로 열리면 명령이 아니라 URI로 실행된 것이다. 문서처럼 `C:\Windows\System32\OpenSSH\ssh.exe` 또는 `scp.exe`를 명시한다.
- `exactly one authorized ADB device` 오류는 기기 없음, 미승인 또는 2대 이상 연결 상태다.
- `AccessibilityService did not bind`이면 Android 보안 정책이 ADB 복원을 막은 경우다. 스크립트가 자동 재시도한 뒤에도 실패했을 때만 사용자가 접근성 설정에서 한 번 허용한다.
- `split manifest does not match`이면 수집하지 말고 운영 담당자에게 알린다.
- N100·A100·Solar·ADB 연결 오류는 탐색 실패 데이터로 바꾸지 않는다.
