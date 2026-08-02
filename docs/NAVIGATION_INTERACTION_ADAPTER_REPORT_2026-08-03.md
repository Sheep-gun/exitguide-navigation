# Navigation Interaction Episode 변환 보고서

## 교정된 결론

기존 Decision DB의 25개 에피소드·74개 행동을 팀 공통 스키마 v0.9.1의 `interaction-episode` JSONL로 변환했다. JSON Schema, 공통 의미 검증기, 원본-결과 round-trip 검사는 모두 통과했고 입력 SQLite의 해시는 변하지 않았다.

처음에는 1.9MB Decision DB만 사용해 전체 후보를 `unavailable`로 기록했다. 이후 Decision DB provenance에 적힌 SHA-256과 정확히 일치하는 legacy 원본 DB를 찾아 다시 연결했다. 그 결과 원본 `candidates_json` 및 실기기 action inventory와 현재 affordance를 74개 step 모두 1:1로 대조할 수 있었다.

따라서 최종 교정 결과는 다음과 같다.

- legacy 원본 없이 변환: `unavailable=74`
- exact-hash legacy 원본을 함께 사용: `complete=74`, `partial=0`, `unavailable=0`

여기서 `complete`는 **당시 원본 후보 추출기가 기록한 후보 집합을 온전히 복원했다**는 의미다. 실제 화면에서 후보 추출기가 놓친 요소까지 없었다는 의미는 아니다.

## 입력 provenance

### Navigation Decision DB v2

- DB: `.artifacts/standardization-pipeline-20260803/navigation-decision-v2.sqlite`
- SHA-256: `b50216838699a19801935b5a98cd5c8d135e75bb065d1f0f890d6dbb28819764`
- Navigation Experience Profile: `exitguide.navigation-experience.v1` / `1.0.0`

### 후보 복구용 legacy DB

- 파일명: `universal-navigation.sqlite`
- SHA-256: `c03452621df17ad3d40472e3bd6634d5a33d8473130f229b02dea43f58dd0c9f`
- Decision DB의 `upstream_legacy_source_sha256`와 일치: PASS
- AndroidControl DB 사용: 없음

두 DB 모두 SQLite `mode=ro`와 `query_only`로 열고 변환 전후 SHA-256을 비교했다.

## 최종 변환 결과

| 항목 | 결과 |
|---|---:|
| Interaction Episode | 25 |
| Step | 74 |
| 고유 화면 fingerprint | 73 |
| 복구한 후보 항목 | 1,537 |
| 화면당 후보 수 최소 / 중앙값 / 최대 | 3 / 19 / 46 |
| Human Gold Episode / Step | 14 / 63 |
| Real-device Episode / Step | 11 / 11 |
| 전체 후보 complete / partial / unavailable | 74 / 0 / 0 |
| click / scroll / stop_for_user | 49 / 11 / 14 |
| click 선택 후보 정확히 1개 포함 | 49 / 49 |
| 비-click에서 selected 후보 0개 | 25 / 25 |
| 후보 ID 중복 화면 | 0 |
| 선택된 forbidden 후보 | 0 |
| 선택된 dangerous-final 후보 | 0 |
| JSON Schema 오류 | 0 |
| 의미 검증 오류 | 0 |
| round-trip 불일치 | 0 |

공통 goal ID 기준 에피소드 수는 다음과 같다.

| 공통 goal_id | Episode |
|---|---:|
| `create_account` | 3 |
| `delete_account` | 4 |
| `join_membership` | 1 |
| `change_membership` | 2 |
| `cancel_membership` | 15 |

사용자가 언급한 Human Gold 21개 전체가 현재 범위에 변환된 것은 아니다. 현재 표준화 DB에서 확인되는 Human Gold는 14개 source record, 63개 step이다. 나머지는 현재 세 목적 범위 밖인지, 원본 반입에서 빠졌는지 별도 inventory 대조가 필요하다.

## 후보 완전성 판정 규칙

한 step을 `complete`로 인정하려면 다음 조건을 모두 통과해야 한다.

1. legacy DB 파일 SHA-256이 Decision DB provenance와 정확히 일치한다.
2. Decision Case의 evidence `source_ref`로 원본 Human Gold example 또는 실기기 attempt를 찾을 수 있다.
3. 원본 후보의 `element_key` 해시와 현재 affordance의 `source_element_key`가 중복 없이 1:1로 일치한다.
4. 원본 후보 수와 현재 affordance 수가 같다.
5. 클릭 step은 선택한 후보가 복구 집합에 정확히 한 번 포함된다.

일부만 일치하면 `partial`, 전혀 검증할 수 없으면 `unavailable`이다. `--require-complete-candidates`를 사용하면 하나라도 `complete`가 아닌 경우 출력 생성 자체가 실패한다.

좌표, 원문 UI dump, 후보 점수, 모델 호출, 검색 hit, latency는 추정해서 채우지 않는다. 후보 payload에는 의미 필드와 원본 modality만 보존한다.

## 산출물

- 고정 계약: `db/contracts/shared_app_knowledge_v0_9_1/`
- 변환기: `scripts/Export-NavigationInteractionEpisodes.py`
- 단위 테스트: `apps/api/tests/navigation_interaction_adapter_unit.py`
- 완전 후보 JSONL: `.artifacts/interaction-episode-candidate-recovery-20260803/interaction-episodes.complete.v1.jsonl`
- 검증 보고서: `.artifacts/interaction-episode-candidate-recovery-20260803/interaction-episodes.complete.v1.report.json`
- JSONL SHA-256: `a4612239dc4dab39922296df5365b36605ae64e2bb0b74ebcb44485302ea0099`

N100 운영 DB에는 아직 반영하지 않았다.

## 남은 한계와 다음 게이트

- 74개 complete step은 knowledge promotion의 **검증 입력**으로 사용할 수 있지만 자동 승격되지는 않는다.
- 과거 기록에는 memory/verifier 점수, 모델 호출, latency, Python 안전 게이트 trace가 없다.
- 위험 후보 0건은 과거 후보 추출 결과에서 발견되지 않았다는 뜻이지, 위험 후보 검출 recall이 완전하다는 뜻은 아니다.
- 다음 단계는 앱 분리 규칙을 유지한 채 기존 Retriever와 complete-candidate Retriever를 같은 74개 화면에서 비교하는 오프라인 A/B다.
- A/B에서는 첫 행동 정확도, 전체 다음 행동 정확도, 잘못된 클릭 수와 앱 누수를 우선 측정한다.
