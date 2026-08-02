# AndroidControl 기반 Navigation 근거

EGL Universal Navigation은 공개 UI 화면 모음인 Rico·MobileViews를 사용하지 않습니다. 공개 사전 근거는 **AndroidControl만** 사용합니다. AndroidControl은 Google Research가 공개한 15,283개 성공 시연으로, 각 에피소드에 전체 목적, 단계 설명, 화면 스크린샷, Android 접근성 트리, 행동이 함께 있습니다.

- 공식 설명·형식: <https://github.com/google-research/google-research/tree/master/android_control>
- 공식 데이터: <https://storage.googleapis.com/gresearch/android_control/>
- 논문: <https://research.google/pubs/on-the-effects-of-data-scale-on-ui-control-agents/>
- 라이선스: Apache License 2.0

## EGL에서 사용하는 정보

원본 약 50GB를 API 요청 때 직접 읽지 않습니다. 변환 시 스크린샷과 실제 입력 문자열을 버리고 다음 필드를 portable SQLite 인덱스에 저장합니다.

```text
episode_id
goal
step_index
step_instruction
action_type
target_text
screen_text
app_name
source_split
screen_function
action_function
next_screen_text
success
went_back
terminal
risk_level
failure_reason
```

같은 episode에서 다음 step의 `screen_text`를 현재 행동의 `next_screen_text`로 연결해 `screen → action → next_screen` 전이를 복원합니다. 성공 시연의 마지막 step은 `terminal=1`, back 행동은 `went_back=1`로 표시하며 결제·삭제·해지·토글 등은 위험도를 별도 기록합니다. AndroidControl 원본은 성공 시연 모음이므로 원본에 없는 실패를 임의로 만들지 않고 `failure_reason`은 비워 둡니다. EGL 런타임에서 발생한 실제 실패는 기능 그래프와 학습 큐에 별도로 쌓입니다.

`goal → screen/function → action → next_screen/function`을 현재 사용자 목적과 화면 후보에 검색해 K-EXAONE 프롬프트에 최대 5개 시연을 제공합니다. 시연은 특정 앱의 고정 경로가 아니라 `계정 진입 → 결제/멤버십 관리 → 해지` 같은 앱 간 공통 기능 순서를 판단하는 참고 근거입니다.

검색은 FTS5 키워드 점수와 64차원 bilingual function-cue 의미 벡터를 결합합니다. 벡터는 외부 서비스 없이 재생성 가능하며, 현재 후보의 기능 태그와 맞지 않는 시연은 점수를 제한합니다.

## 운영 인덱스 현황

2026-08-02 A100 서버 기준:

- 공식 shard: 20/20
- 정규화 행동 단계: 83,848
- FTS 행: 83,848
- 의미 벡터: 83,848 × 64차원
- 스키마: v3
- SQLite `quick_check`: `ok`
- 인덱스 SHA-256: `96d3d47e5e707da66cd5b57f1cc32ab2bade62b647e09d9a28a2b7a6d2875e71`
- 생성 시각: `2026-08-02T01:06:55+00:00`
- 재현·검증 manifest: `fixtures/android-control/official-index-manifest.v3.json`
- 원본 shard는 서버에만 보존하고 Git에는 넣지 않음

API 검색 경로는 실제 운영 설정의 `ANDROID_CONTROL_INDEX_PATH`를 사용한다. retrieval trace에는 AndroidControl 검색 실행 여부, Top-K 근거, K-EXAONE 입력 해시와 최종 Hermes 행동이 함께 남는다.

## 노트북 개발 기준선

휴대폰 없이 인덱서와 에이전트를 검증할 수 있도록 작은 합성 정규화 샘플이 있습니다. 이것은 AndroidControl 원본을 복제한 데이터가 아니라 변환 계약을 검증하기 위한 테스트 fixture입니다.

```powershell
& .\apps\api\.venv\Scripts\python.exe .\scripts\Build-AndroidControlIndex.py `
  --input .\fixtures\android-control\normalized-sample.jsonl `
  --output .\.artifacts\android-control\navigation-examples.sqlite

.\scripts\Test-ApiUnit.ps1
```

K-EXAONE까지 포함한 `구독 탭 ≠ 결제 구독 관리` 회귀 평가는 로컬 `.env` 설정 후 다음으로 실행합니다.

```powershell
& .\apps\api\.venv\Scripts\python.exe .\scripts\Evaluate-AndroidControlNavigation.py
```

기본 API 설정은 아래 인덱스를 자동으로 찾습니다.

```dotenv
ANDROID_CONTROL_INDEX_PATH=.artifacts/android-control/navigation-examples.sqlite
ANDROID_CONTROL_RETRIEVAL_TOP_K=5
NAVIGATION_AGENT_MIN_CONFIDENCE=0.55
NAVIGATION_AGENT_MIN_CANDIDATE_MARGIN=0.07
```

인덱스가 없으면 AndroidControl 검색만 비활성화되고, 기능 의미 분류·K-EXAONE·누적 기능 그래프는 계속 동작합니다.

## 공식 원본 변환

공식 데이터는 20개 GZIP TFRecord이며 각 shard가 약 2.3~2.7GB입니다. 노트북에는 전체를 자동 다운로드하지 않습니다. 아래 명령은 기본적으로 작은 split 메타데이터만 받습니다.

```powershell
.\scripts\Get-AndroidControl.ps1
```

하나의 shard만 명시적으로 받으려면:

```powershell
.\scripts\Get-AndroidControl.ps1 -Shard 0
```

전체 약 50GB는 사용자가 직접 `-All`을 지정한 경우에만 받습니다.

```powershell
.\scripts\Get-AndroidControl.ps1 -All
```

공식 TFRecord 변환기는 저장소에 포함된 경량 GZIP TFRecord·protobuf 스트리밍 디코더를 사용합니다. TensorFlow와 `android_env`를 추가 설치하지 않으며, 거대한 `screenshots` feature는 해석하지 않고 건너뜁니다.

```powershell
& .\apps\api\.venv\Scripts\python.exe .\scripts\Build-AndroidControlIndex.py `
  --format official-tfrecord `
  --input .\.artifacts\android-control\raw\android_control-00000-of-00020 `
  --normalized-output .\.artifacts\android-control\normalized-shard-0.jsonl `
  --output .\.artifacts\android-control\navigation-examples.sqlite
```

변환기는 `input_text`의 실제 입력값을 인덱스에 복사하지 않으며 `text input`으로 치환합니다. 클릭 행동은 좌표를 포함하는 가장 작은 접근성 노드를 찾아 `target_text`로 변환합니다. 이메일·전화번호·토큰 패턴도 SQLite 적재 전에 마스킹합니다.

전체 서버 다운로드·변환은 다음 재현 스크립트로 수행합니다.

```bash
scripts/Get-AndroidControl.sh --all --destination .artifacts/android-control/raw
scripts/Build-AndroidControlServer.sh
```

`Build-AndroidControlServer.sh`는 전이 메타데이터와 의미 벡터를 함께 만들고 최종 파일의 SHA-256과 생성 시각 sidecar를 기록합니다. 기존 v1/v2 인덱스만 승격할 때에는 원본 shard 재다운로드 없이 다음 명령을 사용합니다.

```bash
python scripts/Build-AndroidControlSemanticVectors.py \
  --index .artifacts/android-control/navigation-examples.sqlite
```

서버 종료 전 `Create-NavigationPortableBackup.py`가 이 인덱스, Navigation DB snapshot, 학습 JSONL/SQLite, 평가 결과, 재랭커와 재생성 코드를 하나의 checksum manifest archive로 묶습니다. 20개 원본 shard와 원본 화면 이미지는 archive에서 제외합니다.

## 정확도 가드레일

- 버튼 표면 단어보다 기능 라벨과 예상 다음 화면을 우선합니다.
- 홈 하단의 `구독`은 문맥상 `content_subscriptions`로 분류하여 Premium 결제 해지 후보에서 제외합니다.
- AndroidControl 검색 결과와 현재 후보의 기능이 일치할 때만 근거 점수를 올립니다.
- K-EXAONE이 높은 확신을 주장해도 독립 기능 점수가 낮으면 안내를 중단합니다.
- Hermes 도구 JSON과 후보 선택의 재현성을 위해 K-EXAONE 판단 온도를 0.1로 고정합니다.
- 상위 두 후보의 점수 차이가 기준보다 작으면 임의로 하나를 고르지 않습니다.
- 성공한 실제 EGL 탐색은 별도의 최신 기능 그래프에 축적되며 AndroidControl보다 높은 재사용 신뢰도를 가집니다.
