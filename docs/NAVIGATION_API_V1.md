# Navigation Decision API v1

이 API는 기존 앱별 경로 API와 분리된 실험 런타임이다. Terms RAG를 호출하거나
외부 행동 예시 색인을 읽지 않으며, `NAVIGATION_DECISION_DB_PATH`에 지정된 신규
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

Solar Pro 3 Hermes planner를 사용할 때는 서비스 비밀 환경에서 다음을 설정한다.

```text
NAVIGATION_MODEL_ALLOW_FALLBACK=true
NAVIGATION_PLANNER_MODE=selective
NAVIGATION_VLM_MODE=selective
NAVIGATION_PLANNER_PROVIDER=solar_pro3
NAVIGATION_PLANNER_API_KEY=(service secret)
NAVIGATION_PLANNER_BASE_URL=https://api.upstage.ai/v1
NAVIGATION_PLANNER_MODEL=solar-pro3
EXAONE_VLM_API_KEY=(service secret, local endpoint이면 생략 가능)
EXAONE_VLM_BASE_URL=(EXAONE 4.5 OpenAI-compatible base URL)
EXAONE_VLM_MODEL=EXAONE-4.5-33B
```

API 키는 DB, Git, runtime event payload에 저장하지 않는다.

Solar Pro 3의 런타임 Hermes tool call은 `submit_navigation_step_evaluation` 하나로 제한한다.
한 응답에 검증 가능한 즉시 sub-goal과 현재 허용 행동 전체의 상대 가치를 함께 받아 모델
왕복을 줄인다. 모델은 `best_action_key`를 제시하지만 `click` tool을 직접 호출하지 않는다.
Python은 누락·발명 ID, 0점 동률, 최고 점수와 best key 불일치, 낮은 점수 간격을 거부한
뒤 안전 게이트를 통과한 행동만 반환한다.

`NAVIGATION_PLANNER_MODE`와 `NAVIGATION_VLM_MODE`는 `always`, `selective`, `disabled`
중 하나다. `always`는 연구 A/B용이고, 기본 `selective`는 DB 점수·후보 간격이 충분하지
않거나 무라벨 아이콘·WebView·Canvas·복구 상황일 때만 모델을 호출한다. 정상적으로
`advanced`된 이전 단계는 Solar 호출 사유가 아니다. 관찰된 무변화·역행·실패 화면,
A→B→A 화면 루프, 금지 후보가 생긴 복구 단계만 history 기반 escalation으로 취급한다.
transport/device 오류는 UI 탐색 실패와 분리하며 Solar 호출로 해결하려 하지 않는다.
모델 endpoint가 연결됐다는 이유만으로 매 화면 느린 호출을 강제하지 않는다.

## 계약

- `GET /health`: 프로세스 생존 확인
- `GET /v1/navigation/status`: decision/runtime DB와 planner 준비 상태. 모델 endpoint가
  없으면 `serving_mode=decision_memory_fallback`과 구체적인
  `research_model_blockers`를 반환하며 model-ready로 가장하지 않는다.
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

- K² 계층적 계획: `NavigationPlannerResearchClient.plan_and_verify_actions`의 검증 가능한 즉시 sub-goal
- V-Droid 후보 가치 평가: 동일 Hermes 응답에서 유한 행동 전체를 독립 채점
- DroidRun 행동 후 검증: `verify_transition`
- MobileUse 선택적 복구: action/trajectory/global trigger와 VLM/LLM reflector
- K² Locate/Revise: 첫 실패 단계의 수정 제안을 runtime queue에 격리하고 수동/리플레이 검증 전에는 canonical DB를 수정하지 않음

이는 각 연구의 전체 구현을 복제한 것이 아니라, ExitGuide 제약에 맞춘 최소 수직
프로토타입이다. 성능 우위는 앱 분리 오프라인 리플레이 A/B 결과가 나오기 전까지
주장하지 않는다.
