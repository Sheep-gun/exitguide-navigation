# AndroidControl 기반 Navigation 근거

EGL Universal Navigation은 공개 UI 화면 모음인 Rico·MobileViews를 사용하지 않습니다. 공개 사전 근거는 **AndroidControl만** 사용합니다. AndroidControl은 Google Research가 공개한 15,283개 성공 시연으로, 각 에피소드에 전체 목적, 단계 설명, 화면 스크린샷, Android 접근성 트리, 행동이 함께 있습니다.

- 공식 설명·형식: <https://github.com/google-research/google-research/tree/master/android_control>
- 공식 데이터: <https://storage.googleapis.com/gresearch/android_control/>
- 논문: <https://research.google/pubs/on-the-effects-of-data-scale-on-ui-control-agents/>
- 라이선스: Apache License 2.0

## EGL에서 사용하는 정보

원본 약 50GB를 API 요청 때 직접 읽지 않습니다. 변환 시 스크린샷과 입력 문자열을 버리고 다음 필드만 작은 SQLite FTS5 인덱스에 저장합니다.

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
```

`goal → step_instruction → target_text`를 현재 사용자 목적과 화면 후보에 검색해 K-EXAONE 프롬프트에 최대 5개 시연을 제공합니다. 시연은 특정 앱의 고정 경로가 아니라 `계정 진입 → 결제/멤버십 관리 → 해지` 같은 앱 간 공통 기능 순서를 판단하는 참고 근거입니다.

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

## 정확도 가드레일

- 버튼 표면 단어보다 기능 라벨과 예상 다음 화면을 우선합니다.
- 홈 하단의 `구독`은 문맥상 `content_subscriptions`로 분류하여 Premium 결제 해지 후보에서 제외합니다.
- AndroidControl 검색 결과와 현재 후보의 기능이 일치할 때만 근거 점수를 올립니다.
- K-EXAONE이 높은 확신을 주장해도 독립 기능 점수가 낮으면 안내를 중단합니다.
- Hermes 도구 JSON과 후보 선택의 재현성을 위해 K-EXAONE 판단 온도를 0.1로 고정합니다.
- 상위 두 후보의 점수 차이가 기준보다 작으면 임의로 하나를 고르지 않습니다.
- 성공한 실제 EGL 탐색은 별도의 최신 기능 그래프에 축적되며 AndroidControl보다 높은 재사용 신뢰도를 가집니다.
