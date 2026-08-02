# Navigation Interaction Episode 변환 보고서

## 결론

기존 Decision DB의 25개 에피소드·74개 행동을 팀 공통 스키마 v0.9.1의 `interaction-episode` JSONL로 손실 검사와 함께 변환했다. JSON Schema, 공통 의미 검증기, 원본-결과 round-trip 검사는 모두 통과했고 원본 SQLite 해시는 변하지 않았다.

다만 이 변환만으로 신규 Retriever 학습 데이터가 충분해진 것은 아니다. 기존 기록에는 각 화면의 **전체 후보 목록**이 없으므로 74개 행동 전부 `candidate_set_status=unavailable`이다. 따라서 현재 결과는 경험 보존·오프라인 리플레이 입력으로는 사용할 수 있지만 canonical transition으로 자동 승격하거나 후보 선택 정확도 학습의 정답으로 쓰면 안 된다.

## 기준 입력

- DB: `.artifacts/standardization-pipeline-20260803/navigation-decision-v2.sqlite`
- SHA-256: `b50216838699a19801935b5a98cd5c8d135e75bb065d1f0f890d6dbb28819764`
- Navigation Experience Profile: `exitguide.navigation-experience.v1` / `1.0.0`
- 기존 legacy 원본 SHA-256: `c03452621df17ad3d40472e3bd6634d5a33d8473130f229b02dea43f58dd0c9f`

최신 표준화 산출물을 기준으로 선택했다. 이전 integration 사본도 74건이지만 화면·affordance 식별자가 달라 감사 보고서와 연결되는 최신 표준화본을 우선했다.

## 변환 결과

| 항목 | 결과 |
|---|---:|
| Interaction Episode | 25 |
| Step | 74 |
| Human Gold Episode / Step | 14 / 63 |
| Real-device Episode / Step | 11 / 11 |
| 전체 후보 complete / partial / unavailable | 0 / 0 / 74 |
| 자동 승격 가능 Step | 0 |
| click / scroll / stop_for_user | 49 / 11 / 14 |
| JSON Schema 오류 | 0 |
| 의미 검증 오류 | 0 |
| round-trip 불일치 | 0 |
| 위험한 최종 클릭 | 0 |

공통 goal ID 기준 에피소드 수는 다음과 같다.

| 공통 goal_id | Episode |
|---|---:|
| `create_account` | 3 |
| `delete_account` | 4 |
| `join_membership` | 1 |
| `change_membership` | 2 |
| `cancel_membership` | 15 |

사용자가 언급한 Human Gold 21개 전체가 현재 범위에 변환된 것은 아니다. 현재 표준화 DB에서 실제로 확인되는 Human Gold는 14개 source record, 63개 step이다. 나머지는 현재 세 목적 범위 밖인지, 원본 반입에서 빠졌는지 별도 inventory 대조가 필요하다.

## 적용한 보존 규칙

1. 기존 Navigation goal ID는 `navigation-goal-crosswalk.v1.json`의 exact mapping만 사용했다.
2. 클릭의 후보 ID는 affordance가 보존한 원래 `candidate_key`를 사용했다.
3. 전체 후보, 후보 점수, 검색 hit, 모델 호출, latency, 안전 게이트 trace는 추정하지 않았다.
4. 연결 실패는 탐색 실패로 바꾸지 않는다. transport 계열 상태에는 다음 화면과 진행 판정을 허용하지 않는다.
5. 과거 문자열의 mojibake는 임의 복구하지 않고 원본 그대로 보존했다.
6. source DB는 SQLite `mode=ro`와 `query_only`로 열고 변환 전후 SHA-256을 비교했다.
7. 출력의 step ordinal은 에피소드 내부에서 0부터 연속되도록 정규화하고, 원래 ordinal은 보고서의 `step_mappings`에 보존했다.

## 산출물

- 고정 계약: `db/contracts/shared_app_knowledge_v0_9_1/`
- 변환기: `scripts/Export-NavigationInteractionEpisodes.py`
- 단위 테스트: `apps/api/tests/navigation_interaction_adapter_unit.py`
- 로컬 JSONL: `.artifacts/interaction-episode-export-20260803/interaction-episodes.v1.jsonl`
- 로컬 검증 보고서: `.artifacts/interaction-episode-export-20260803/interaction-episodes.v1.report.json`
- JSONL SHA-256: `1ba33fdd444fd0ffc542f67317a4362d7e06892776ab947955e929a67c4c6db4`

N100 운영 DB에는 아직 반영하지 않았다.

## 테스트 상태

- PASS: `navigation_interaction_adapter_unit.py`
- PASS: 실제 25 Episode / 74 Step 변환
- PASS: `navigation_decision_memory_unit.py`
- PASS: `navigation_experience_profile_unit.py`
- PASS: `navigation_runtime_unit.py`
- FAIL: `navigation_research_architecture_unit.py`

마지막 실패는 이번 변환기의 데이터·계약 오류가 아니다. 현재 runtime이 새 Solar Goal Ontology 분류 호출을 먼저 수행하지만 해당 기존 테스트의 fake model이 그 system prompt를 처리하지 못해 중단된다. runtime 테스트 픽스처를 새 분류 계약에 맞추는 별도 수정이 필요하다.

## 다음 개발 게이트

다음 단계는 74건을 그대로 학습시키는 일이 아니다. 기록된 화면을 오프라인 재생해 Accessibility/OCR/VLM 후보 추출기를 실행하고, 각 화면의 전체 후보를 실제 관찰값으로 채운 새 Episode를 만들어야 한다. `candidate_set_status=complete` 사례가 확보된 뒤에만 knowledge promotion과 신규 Retriever A/B 평가로 넘어간다.
