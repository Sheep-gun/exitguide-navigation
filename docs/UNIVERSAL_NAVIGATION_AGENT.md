# 범용 EGL Navigation Agent

> 범용 기능 DB의 자동 생성 벤치마크, frozen holdout, adversarial 검사, 실패 분류와 K-EXAONE 검토 후보 생성은 [Navigation DB Gym](NAVIGATION_DB_GYM.md)을 기준으로 운영한다.

이 브랜치의 Navigation Agent는 앱별 모범 경로를 미리 요구하지 않습니다. 처음 보는 Android 앱을 제한 시간 안에서 탐색해 **최종 목적 기능을 먼저 확정**하고, 발견한 화면·메뉴·전이를 SQLite 기능 그래프로 축적합니다. 탐색 중에는 상태를 바꾸지 않는 저위험 메뉴만 자동으로 열 수 있습니다. 최종 기능이 있는 화면을 찾으면 최종 버튼은 누르지 않고 탐색과 플로팅 서비스를 자동 종료합니다. 처음 발견한 경로는 곧바로 재사용하지 않으며, 독립 검토로 목적지와 안전 정지가 확인된 `verified_candidate`만 같은 앱·버전·locale·목적에서 저위험 중간 메뉴를 자동 재사용합니다. 최종 버튼은 항상 사용자가 직접 누릅니다. AndroidControl의 목적·단계·행동 시연은 앱 간 기능 판단의 사전 근거로 사용하며 Rico·MobileViews는 사용하지 않습니다.

전체 흐름은 [EGL Navigation 파이프라인 SVG](EGL_NAVIGATION_PIPELINE.svg)에서 볼 수 있습니다.

## 동작 경계

- `AccessibilityService`는 보이는 노드의 텍스트, 역할, 클릭 가능 여부, 상태, 화면 좌표를 읽습니다.
- 비밀번호 및 편집 입력창의 내용은 API로 보내지 않습니다.
- K-EXAONE에는 현재 화면에서 실제로 클릭 가능한 후보 ID만 허용목록으로 전달합니다.
- 버튼 이름뿐 아니라 화면 위치, 부모·주변 문맥, 기능 라벨, AndroidControl 유사 시연을 함께 전달합니다.
- K-EXAONE은 Hermes/OpenAI 도구 `recommend_navigation_action`을 반드시 호출합니다.
- 서버는 모델이 허용목록 밖의 ID를 반환하면 거부합니다. 빈 선택·근거 없는 완료 판정·현재 화면 의미 점수와 크게 충돌하는 선택도 가드레일이 교정합니다.
- K-EXAONE이 늦거나 불안정하면 결정론적 폴백으로 현재 화면의 안전한 후보를 계속 안내합니다.
- 앱 본체의 `탐색 시작`은 자동 조작을 곧바로 실행하지 않고, 안내 말풍선과 원형 `▶` 버튼을 표시하는 대기 상태만 엽니다. 사용자가 대상 앱을 직접 연 뒤 `▶`를 눌러야 `operation_mode=explore`가 활성화됩니다.
- `operation_mode=explore`를 사용자가 명시적으로 시작한 동안에만 저위험 탐색 메뉴의 자동 클릭·스크롤·뒤로가기를 허용합니다.
- 자동 클릭은 기능 DB의 `safe_navigation`, API의 `safe_to_execute`, 현재 후보의 `low` 위험도, 비체크박스·비스위치·비입력창 조건을 모두 통과해야 합니다.
- 해지·삭제·결제·환불·동의·권한 변경 등 `never_auto` 또는 상태 변경 기능은 탐색의 최종 목적 후보로만 인식하며 자동으로 누르지 않습니다.
- 경로 발견, 탐색 중단, 목적 화면 도착 중 하나가 발생하면 APK의 탐색 활성 상태를 해제합니다. 목적 화면 도착 시 플로팅 서비스도 자동 종료되며, 늦게 도착한 이전 응답은 추가 클릭을 실행할 수 없습니다.
- 새 경로는 `shadow`로 저장합니다. 독립 검토를 통과한 `verified_candidate`만 저위험 중간 메뉴에 한해 자동 재사용하며, 형식상 `approved` 승격은 별도의 명시적 검토와 충분한 표본 없이는 수행하지 않습니다.
- 검증 후보 재사용 중 버튼·화면 의미가 달라지면 최대 두 번의 관찰 안에 해당 경로를 `stale`로 폐기하고 같은 세션에서 범용 탐색으로 복귀합니다.

## 실행 흐름

```text
목적 입력 → 탐색 시작 → 안내 말풍선과 ▶ 버튼 표시
    ↓
사용자가 대상 앱을 직접 열고 ▶ 버튼을 누름
    ↓
기능 사전에서 최종 기능 ID 확정
    ↓
현재 앱·버전·locale의 저장 경로 조회
    ├─ 검증 후보 있음 → 저위험 중간 메뉴만 최대 2회 자동 재사용
    │                    ├─ 화면 의미 일치 → 다음 검증 단계 진행
    │                    └─ 불일치 → 최대 2회 관찰 안에 폐기 후 범용 탐색
    └─ 검증 후보 없음 → 최대 55초/16회/깊이 9의 안전 탐색
                       ├─ 접근성 트리에서 버튼·부모·주변 문맥 분석
                       ├─ 기능 사전 + AndroidControl 의미 점수 계산
                       ├─ 안전 후보가 비슷할 때만 K-EXAONE Hermes로 재판단
                       ├─ 저위험 탐색 메뉴만 자동 클릭
                       ├─ 화면에 후보가 없으면 최대 4회 자동 스크롤
                       └─ 막힌 분기는 자동 뒤로가기로 DFS 백트래킹
    ↓
최종 기능 후보 발견(최종 버튼은 누르지 않음)
    ↓
경로 저장 → 자동 터치 OFF → 플로팅 서비스 종료
    ↓
다음 실행부터 검증된 동일 버전 경로의 저위험 중간 메뉴만 빠르게 재사용
    ↓
성공·실패 전이 통계를 업데이트하고 앱 업데이트 시 경로를 재검증
```

## 기능 그래프

런타임은 두 SQLite DB를 사용하며 둘 다 `.artifacts/` 아래에 생성되고 Git에는 포함하지 않습니다.

### 1. 교차 앱 기능 의미 DB

검토 가능한 원본은 `fixtures/navigation/function-catalog.v1.json`, 빠른 런타임 DB는 `.artifacts/navigation-function-catalog.sqlite`입니다. DB는 버전과 원본 SHA-256을 함께 확인해 내용이 바뀌면 자동 재적재합니다. 현재 canonical은 v15(`catalog_version = 15.0.0`, SHA-256 `e0eeef03195a48ec8172421926d08c30823bc678c72ea72082bb513dbec36e24`)이며 179개 영역, 2,866개 물리 기능, 2,660개 물리 intent를 포함합니다. 동등성 오버레이를 적용하면 2,856개 논리 기능·2,650개 논리 intent이며, canonicalize한 고유 default terminal은 2,648개입니다. 배달의민족의 `마이배민`, `배민클럽 이용 중`, `마이배민클럽`, `해지하기`처럼 앱 고유 명칭도 범용 기능 의미에 연결하되 화면 좌표나 고정 경로로 저장하지 않습니다.

독립 참조 자료는 20개 팩, 4,645개 사례, 12,007개 단계로 물리 기능·intent를 100% 참조합니다. 이는 **참조 커버리지**이지 resolver 정확도가 아닙니다. 기권 사례를 제외한 독립 목적 4,405개를 실제 resolver로 판정한 v15 기준선은 1,092개 정답(24.79%)이며 신규 v15 분할은 840개 중 125개(14.88%)입니다. 두 수치 모두 실제 Android 기기의 UI·OCR·조작 정확도를 입증하지 않으며, 실기기 정확도는 사람이 검증한 `real_device_gold`로 별도 측정합니다.

회원가입은 단일 버튼 하나가 아니라 `가입 진입 → 가입 방식(이메일·휴대폰·소셜) → 본인 인증 → 가입 약관 → 필수·선택 동의 → 프로필·권한·관심사 초기 설정 → 가입 완료`로 세분화했습니다. 로그인, 게스트 이용, 2단계 인증도 별도 목적과 기능으로 구분합니다. 가입 진입처럼 상태를 바꾸지 않는 화면 이동만 안전 탐색 후보이며, 약관 동의·권한 허용·정보 제출·가입 완료는 항상 사용자가 직접 선택합니다.

### 교차 앱 공통 메뉴 관문

기능 사전 v1.4부터 앱별 고정 경로와 별개로 여러 앱에서 반복되는 공통 관문을 JSON 원본과 SQLite 런타임 인덱스에 저장합니다. 대표 관문은 `전체메뉴`, `마이페이지`, `로그인·회원가입`, `로그인 화면 진입`, `설정`입니다. 목적 경로에 `account.entry` 또는 `settings.root`가 포함되면 `전체메뉴`를 앞단 후보로 자동 확장하고, 회원가입 목적이면 다음 범용 후보군을 사용합니다.

`전체메뉴 → 마이페이지 → 로그인/회원가입 → 회원가입`

이 순서는 강제 경로가 아닙니다. 현재 화면에 존재하는 후보만 점수화하며, 더 직접적인 후보가 있으면 중간 관문을 생략합니다. `로그인/회원가입`처럼 두 기능이 결합된 버튼은 중간 관문으로 보고 자동 탐색할 수 있지만, 로그인 폼에 아이디·비밀번호 입력란이 보이면 `로그인` 버튼은 제출 동작으로 간주하여 자동으로 누르지 않습니다. 따라서 제주항공처럼 별도 앱 경로가 없는 경우에도 마이페이지와 계정 허브를 거쳐 순수 `회원가입` 버튼을 최종 목적지로 찾을 수 있습니다.

- `navigation_functions`: 기능 ID, 도메인, 설명, 위험도, 자동화 정책, 최종 목적 여부, 상태 변경 여부
- `navigation_aliases`: 한국어·영어 버튼명과 정규화 문자열
- `navigation_contexts`: 같은 이름을 구분하는 긍정·부정 주변 문맥
- `navigation_function_legacy_tags`: 기존 AndroidControl 기능 태그 호환 매핑
- `navigation_intents`, `navigation_intent_patterns`: 사용자 문장을 목적 유형과 최종 기능으로 변환
- `navigation_intent_route`, `navigation_function_edges`: 목적에 유익한 중간 기능과 의미상 선후 관계
- `navigation_intent_avoid`: 콘텐츠 구독과 결제 구독처럼 혼동하면 안 되는 기능

예를 들어 `구독`이 화면 하단에서 `홈·Shorts·보관함`과 함께 나타나면 `content.subscriptions`, `결제·멤버십·다음 결제` 문맥에 나타나면 `subscription.manage`로 분리합니다. 정확한 앱별 좌표는 저장하지 않습니다.

### 2. 앱별 관찰·경로 그래프

기본 DB는 `.artifacts/universal-navigation.sqlite`입니다.

- `universal_apps`: 패키지·버전·locale 관찰 기록
- `universal_screens`: 개인정보를 정리한 화면 의미 구조
- `universal_actions`: 화면별 클릭 후보와 위험도
- `universal_transitions`: 사용자가 수행한 행동과 다음 화면
- `universal_sessions`, `universal_session_steps`: 목적별 탐색 기록
- `universal_action_goal_stats`: 완료된 탐색에서 목적별 성공 행동 통계
- `universal_explorations`: 시간·행동·깊이 예산, 현재 탐색 상태, 시작·목적 화면, 현재 DFS 경로
- `universal_exploration_attempts`: 자동 탐색에서 시도한 메뉴, 기능 분류, 성공·실패·다음 화면
- `universal_routes`: 앱 패키지·버전·locale·최종 기능별 발견 경로와 신뢰도
- `universal_app_function_routes`: 앱·버전·기능 도메인(`account`, `subscription`, `notification` 등)별 경로를 분류한 경량 서빙 인덱스. `verified_candidate`와 `approved`만 서빙 대상으로 표시
- `navigation_sessions`, `navigation_stage_timings`: 목적지 확정 시간과 단계별 서버·OCR·조작·외부 대기 시간
- `graph_edge_performance`, `route_performance`: 간선·경로별 성공·안전·p50·p90 성능
- `app_version_signatures`, `route_rankings`: 앱 버전 경계와 안전 우선 최적·예비 경로 순위

화면 fingerprint는 변동하기 쉬운 Android 노드 ID가 아니라 순서가 있는 라벨·역할·상태를 사용합니다. 앱 업데이트로 resource ID가 바뀌어도 같은 의미의 화면과 버튼을 텍스트·역할 유사도로 다시 연결합니다. 유사한 버튼이 둘 이상이라 안전하게 구분되지 않으면 캐시를 사용하지 않고 다시 판단합니다.

경로 생명주기는 `shadow → verified_candidate → approved`로 분리됩니다. `shadow`는 탐색으로 발견됐을 뿐 정답으로 간주하지 않습니다. `verified_candidate`는 사람이 목적지와 안전 정지를 독립 확인한 임시 재사용 단계이며, 앱 버전이 달라지거나 현재 화면 의미가 어긋나면 사용하지 않습니다. 자동 재사용 대상은 보이고 활성화된 저위험·비체크·비입력 중간 메뉴뿐이고, 해지 확정·알림 토글·결제·삭제 등 최종 상태 변경은 경로에 있더라도 실행하지 않습니다.

온라인 조회 우선순위는 `승인된 앱별 기능 경로 → 검증 후보 앱별 기능 경로 → 같은 앱의 관찰 그래프 → 범용 기능 카탈로그 → AndroidControl → K-EXAONE 의미 동률 해소`입니다. K-EXAONE이 원시 SQLite 전체를 직접 검색하는 구조가 아니라, 백엔드가 앱·버전·목적 기능으로 먼저 정밀 조회한 작은 후보만 모델에 전달합니다. 검증 경로가 현재 화면에 맞으면 AndroidControl 검색과 모델 호출을 모두 생략합니다.

실패·중복·미검증 관찰은 서빙 인덱스에서 제외하지만 즉시 삭제하지 않습니다. 이것들은 같은 오답 분기를 반복하지 않게 하는 학습 근거이기 때문입니다. 다음 명령은 원본 DB를 먼저 백업한 뒤 앱별 기능 서빙 인덱스를 재구축하고 SQLite 통계를 최적화합니다.

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\Optimize-NavigationServingDb.py `
  .\.artifacts\universal-navigation.sqlite --apply
```

독립 검토가 끝난 실기기 세션은 다음처럼 명시 확인해야만 후보로 만들 수 있습니다. 과거 APK가 앱 버전을 보내지 않은 세션은 기기 패키지 정보와 설치 갱신 시각으로 당시 버전을 별도 확인한 뒤 `--app-version`을 입력합니다. 이미 저장된 버전은 다른 값으로 덮어쓸 수 없습니다.

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\Verify-NavigationRouteCandidate.py `
  --database .\.artifacts\universal-navigation.sqlite `
  --session-id <reviewed-session-id> `
  --app-version <independently-checked-version> `
  --confirm-reviewed I_REVIEWED_THE_DESTINATION_AND_SAFETY
```

이 명령은 클릭·Back·목적지 정지를 모두 포함한 경로를 다시 구성하고 `verified_candidate`까지만 설정합니다. 정식 `approved` 승격은 수행하지 않습니다.

## API

관찰 및 다음 메뉴 추천:

```http
POST /v1/navigation/agent/observe
```

핵심 입력은 `session_id`, `app_package`, `goal_text`, `operation_mode`, `screen.elements`입니다. `guide`는 자동 조작이 전혀 없는 기본값이고 `explore`는 사용자가 시작한 제한 탐색입니다. 응답의 `phase`, `automation.safe_to_execute`, `discovered_route`가 APK의 실행 가능 범위를 결정합니다. 직전에 버튼을 눌렀다면 `transition`에 이전 `screen_fingerprint`, `performed_element_id`, 결과를 함께 보냅니다.

기능 사전 조회:

```http
GET /v1/navigation/functions?query=구독%20해지
```

누적 그래프 조회:

```http
GET /v1/navigation/agent/graph?app_package=com.example.app
```

실제 기기 탐색 성능 조회:

```http
GET /v1/navigation/agent/performance?measurement_source=real_device
```

`observe`의 선택 입력 `client_timing`과 응답 `performance`는 탐색 시작부터 목적지 확정까지의 시간을 OCR, 자동 조작, UI 안정화, 외부 앱 대기, 서버·DB·모델 판단으로 분리한다. 경로 최적화는 정확도와 안전 정지를 먼저 통과한 경로끼리만 TCD p90·p50을 비교한다. 자세한 정책은 [목적지 탐색 시간 최적화](NAVIGATION_TIME_OPTIMIZATION.md)를 참고한다.

서버 설정:

```dotenv
NAVIGATION_AGENT_PROVIDER=exaone
NAVIGATION_AGENT_ALLOW_FALLBACK=true
NAVIGATION_AGENT_TIMEOUT_SECONDS=10
NAVIGATION_GRAPH_DB_PATH=
NAVIGATION_FUNCTION_DB_PATH=
NAVIGATION_FUNCTION_CATALOG_PATH=
NAVIGATION_EXPLORATION_TIMEOUT_SECONDS=55
NAVIGATION_EXPLORATION_MAX_ACTIONS=16
NAVIGATION_EXPLORATION_MAX_DEPTH=9
ANDROID_CONTROL_INDEX_PATH=.artifacts/android-control/navigation-examples.sqlite
ANDROID_CONTROL_RETRIEVAL_TOP_K=5
NAVIGATION_AGENT_MIN_CONFIDENCE=0.55
NAVIGATION_AGENT_MIN_CANDIDATE_MARGIN=0.07
```

K-EXAONE 키·모델·endpoint는 기존 `EXAONE_*` 환경 변수를 사용합니다. 키는 APK에 넣지 않고 FastAPI 서버에만 둡니다. 로컬 기본 제한은 10초이며, 공개 서버 배포는 네트워크 지연을 고려해 35초를 사용합니다. 제한 안에 응답하지 않으면 안전 폴백으로 전환합니다.

AndroidControl 원본·변환·인덱스 절차는 [ANDROID_CONTROL](ANDROID_CONTROL.md)을 참고합니다. API 인덱스에는 스크린샷을 넣지 않고 목적, 단계 설명, 행동 유형, 대상 UI 문구, 정리된 화면 문맥만 보관합니다.

접근성 트리에는 민감한 화면 문구가 포함될 수 있으므로 릴리스 APK는 일반 HTTP를 차단합니다. 예외는 USB 포트 터널용 loopback(`localhost`, `127.0.0.1`)과 Android 에뮬레이터 호스트(`10.0.2.2`)뿐입니다.

## Android 실행

일반 사용자용 Release APK는 공개 HTTPS 백엔드를 기본으로 사용하고 GitHub 런타임 설정에서 변경된 주소를 자동으로 갱신합니다. 따라서 사용자는 USB, ADB, 노트북 서버 없이 APK와 인터넷 연결만으로 사용할 수 있습니다. 서버 운영 절차는 [PUBLIC_APK_DEPLOYMENT](PUBLIC_APK_DEPLOYMENT.md)를 참고합니다.

1. API를 실행합니다. USB 개발 중에는 `adb reverse tcp:8010 tcp:8010`을 설정하고 앱 주소로 `http://127.0.0.1:8010`을 사용합니다. Wi-Fi 또는 외부망에서는 HTTPS 주소를 사용합니다.
2. 로컬 APK를 빌드합니다.

```powershell
.\scripts\Build-AndroidLocal.ps1 -Variant Release
```

3. 앱에서 API 주소와 목적을 입력합니다.
4. `화면 위 표시` 권한과 `ExitGuide Navigation` 접근성 서비스를 사용자가 직접 켭니다.
5. `탐색 시작`을 누르면 자동 탐색 대신 안내 말풍선과 원형 `▶` 버튼이 나타납니다.
6. 사용자가 대상 앱을 직접 열고 `▶`를 누르면 로딩 아이콘으로 바뀌며 저위험 메뉴의 자동 탐색이 시작됩니다.
7. 화면에 목적 후보가 없으면 접근성 스크롤을 우선 실행하고, 지원하지 않는 화면에서는 실제 위쪽 스와이프 제스처를 사용합니다.
8. 최종 목적 후보를 찾으면 해당 버튼을 자동으로 누르지 않고 탐색과 플로팅 서비스를 종료합니다. 독립 검토를 통과한 경로는 같은 앱 버전에서 저위험 중간 메뉴만 빠르게 재사용하며 최종 동작은 계속 사용자에게 맡깁니다.

로컬 빌드는 JDK 17과 Android 36 SDK, Build Tools 35/36, NDK 27.1.12297006을 사용합니다. Windows에서는 NDK의 `clang++.exe`가 정상 동작하도록 SDK 경로에 공백을 두지 않습니다. 기본 탐색 위치는 `%USERPROFILE%\ExitGuideAndroidSdk`입니다.

## 검증

```powershell
.\scripts\Test-ApiUnit.ps1
cd apps\mobile
npm run typecheck
```

테스트는 기능 사전 적재와 문맥 동음이의어 분리, 처음 보는 패키지의 안전 탐색, 최종 버튼 자동 클릭 금지, 탐색 예산 중단, 시작 화면 복귀, 검증 후보의 저위험 경로 재사용, 두 관찰 이내 stale 폐기와 범용 탐색 복귀, 위험 동작 확인, 개인정보 마스킹, Hermes 도구 계약, 잘못된 모델 ID 폴백, 앱 업데이트로 노드 ID가 바뀐 경우의 의미 재연결, 실제 FastAPI JSON 계약을 확인합니다.

`fixtures/navigation/cross-app-menu-benchmark.v1.json`은 앱별 경로 없이 공통 메뉴 DB만으로 판단하는 10개 목적군·33개 화면 단계의 소규모 회귀 기준선입니다. 현재 v15도 33개 단계를 계속 통과해야 하며, 새 별칭이나 기능 연결을 추가할 때 하나라도 회귀하면 전체 API 검사도 실패합니다. 이 고정 합성 기준선의 통과는 독립 resolver 정확도나 실기기 성능 주장이 아니며, 더 넓은 분할별 평가는 [Navigation DB Gym](NAVIGATION_DB_GYM.md)이 담당합니다.

2026-07-27 합성 미지 앱 화면 10건의 최신 실측값:

- 결정론적 폴백 Top-1: 10/10
- 실제 K-EXAONE + 의미 가드레일 + 폴백 최종 Top-1: 10/10
- 현재 후보 허용목록 준수: 10/10
- 10초 안 K-EXAONE 판단을 그대로 채택: 4/10
- 폴백 포함 평균 응답 시간: 8.10초

같은 날 가드레일 적용 전 별도 실행에서는 최종 Top-1이 6/10까지 흔들렸습니다. 따라서 위 10/10은 모델 단독 성능이 아니라 **현재 화면 허용목록, 결정론적 의미 점수, 타임아웃 폴백을 합친 전체 시스템 결과**입니다. 이 수치는 고정 합성 화면의 연결·안전 기준선이며 실제 앱 일반화 정확도를 의미하지 않습니다. 같은 평가를 다시 실행하려면 로컬 `.env` 설정 후 다음 명령을 사용합니다.

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\Evaluate-UniversalNavigationLive.py
```

## 알려진 한계

- WebView, Canvas, 게임 UI처럼 접근성 라벨이 없는 화면은 읽을 수 있는 후보가 부족할 수 있습니다.
- 로그인 뒤에만 보이는 메뉴는 사용자가 로그인한 상태에서 관찰해야 합니다.
- 한 번도 열지 않은 하위 메뉴 전체를 APK 파일만으로 완전 열거하지는 않습니다. 화면을 탐색하면서 그래프가 자랍니다.
- 현재 화면의 안전 후보가 불명확하고 K-EXAONE도 구분하지 못하면 자동 탐색을 중단합니다.
- 같은 화면에서 아래쪽 메뉴를 찾기 위해 최대 12회 자동 스크롤하지만, 무한 스크롤·가상화 목록·WebView에서는 끝까지 확인하지 못할 수 있습니다.
- 로그인·본인인증 뒤 화면, 외부 브라우저로 넘어가는 결제 흐름은 별도 사용자 입력이 필요할 수 있습니다.
- 실제 기기 검증 전에는 제조사별 접근성 이벤트 차이와 백그라운드 제한을 최종 보장할 수 없습니다.
