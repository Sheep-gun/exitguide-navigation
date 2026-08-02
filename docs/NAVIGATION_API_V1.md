# Navigation Decision API v1

이 API는 기존 앱별 경로 API와 분리된 실험 런타임이다. Terms RAG를 호출하거나
AndroidControl 색인을 읽지 않으며, `NAVIGATION_DECISION_DB_PATH`에 지정된 신규
의사결정 메모리만 읽는다.

## 저장 경계

- Decision memory DB: 읽기 전용, 검증된 ontology/signature/screen/case/outcome 근거
- Runtime DB: 결정과 직후 관찰을 append-only로 기록하는 검증 대기 영역
- Runtime 기록은 오프라인 평가와 승격 검증 전까지 Retriever 근거로 사용하지 않는다.

이 분리는 실패한 모델 출력을 다시 모델의 정답 근거로 검색하는 자기강화 오염을 막는다.

## 실행

```bash
cd apps/api
export NAVIGATION_DECISION_DB_PATH=/absolute/path/navigation-decision-v1.sqlite
export NAVIGATION_RUNTIME_DB_PATH=/absolute/path/navigation-runtime-v1.sqlite
uvicorn app.navigation_main:app --host 127.0.0.1 --port 8100
```

K-EXAONE Hermes planner를 사용할 때는 서비스 비밀 환경에서 다음을 설정한다.

```text
NAVIGATION_MODEL_ALLOW_FALLBACK=true
EXAONE_API_KEY=(service secret)
EXAONE_BASE_URL=(OpenAI-compatible chat completions base URL)
EXAONE_MODEL=LGAI-EXAONE/K-EXAONE-236B-A23B
EXAONE_VLM_API_KEY=(service secret, local endpoint이면 생략 가능)
EXAONE_VLM_BASE_URL=(EXAONE 4.5 OpenAI-compatible base URL)
EXAONE_VLM_MODEL=LGAI-EXAONE/EXAONE-4.5-33B
```

API 키는 DB, Git, runtime event payload에 저장하지 않는다.

K-EXAONE의 Hermes tool call은 `submit_navigation_subgoal`과
`score_navigation_candidate`로 제한된다. `click` tool을 모델에 직접 노출하지 않으며,
점수가 가장 높은 열거 후보를 Python이 고른 뒤 안전 게이트를 통과시킨다. 따라서 모델은
좌표나 화면에 없는 candidate ID를 실행 요청으로 만들 수 없다.

## 계약

- `GET /health`: 프로세스 생존 확인
- `GET /v1/navigation/status`: decision/runtime DB와 planner 준비 상태
- `POST /v1/navigation/decide`: 현재 화면 후보 중 안전한 다음 행동 하나 결정
- `POST /v1/navigation/observe`: 실행 직후 화면 변화·연결 상태 기록 및 복구 제안

`decide` 입력 후보에는 좌표 필드가 존재하지 않으며 unknown 필드도 거부된다. 클릭
출력은 입력에 실제로 있던 `candidate_id`만 허용된다.

허용 행동은 다음 다섯 개뿐이다.

```text
click(candidate_id)
scroll(up|down)
back()
wait_and_observe()
stop_for_user()
```

중간·고위험 후보, 차단 후보, 탈퇴·해지·결제·구매·개인정보 제출의 최종 행동은
Python 안전 게이트가 `stop_for_user()`로 교체한다.

## 연구 구조의 코드 대응

- K² 계층적 계획: `KExaoneResearchClient.plan`과 검증 가능한 즉시 sub-goal
- V-Droid 후보 가치 평가: 유한 후보 열거 후 `KExaoneResearchClient.verify_action`을 후보마다 호출
- DroidRun 행동 후 검증: `verify_transition`
- MobileUse 선택적 복구: action/trajectory/global trigger와 VLM/LLM reflector
- K² Locate/Revise: 첫 실패 단계의 수정 제안을 runtime queue에 격리하고 수동/리플레이 검증 전에는 canonical DB를 수정하지 않음

이는 각 연구의 전체 구현을 복제한 것이 아니라, ExitGuide 제약에 맞춘 최소 수직
프로토타입이다. 성능 우위는 앱 분리 오프라인 리플레이 A/B 결과가 나오기 전까지
주장하지 않는다.
