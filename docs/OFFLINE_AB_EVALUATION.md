# 오프라인 A/B 평가 보고서 — 2026-08-03

## 결론

표준 profile 적용 전 v1과 적용 후 v2 Retriever의 다음 행동 결과는 완전히 동일했다. 현재 변경만으로는 선택 정확도 개선이 없다.

따라서 정적 데이터를 추가하지 않는다. 먼저 완전 후보 inventory를 Retriever 점수 계산에 연결하는 구조 수정이 필요하다.

## 평가 계약

동일한 74개 Decision Case를 다음 두 DB에서 각각 실행했다.

- A — baseline: `navigation-decision-v1.sqlite`
- B — standards profile: `navigation-decision-v2.sqlite`

공통 조건은 다음과 같다.

- 같은 화면과 같은 전체 affordance 후보 사용
- 검색에서 평가 case의 source app 완전 제외
- 앱 split 유지: train 42, validation 13, test 19
- 모델 endpoint 미사용, decision-memory fast/fallback 경로만 평가
- Human Gold 경로 재생 없음
- 각 화면에서 다음 행동 하나를 새로 선택

실행 명령:

```powershell
python scripts\Evaluate-NavigationRuntimeOffline.py `
  --db .artifacts\standardization-pipeline-20260803\navigation-decision-v1.sqlite `
  --output .artifacts\offline-ab-20260803\baseline-v1.json

python scripts\Evaluate-NavigationRuntimeOffline.py `
  --db .artifacts\standardization-pipeline-20260803\navigation-decision-v2.sqlite `
  --output .artifacts\offline-ab-20260803\profile-v2.json
```

## 결과

| 지표 | v1 baseline | v2 profile | 변화 |
|---|---:|---:|---:|
| 목적 인식률 | 1.0000 | 1.0000 | 0 |
| 첫 행동 정확도 | 0.7778 (9건) | 0.7778 (9건) | 0 |
| positive 다음 행동 exact accuracy | 0.4286 (63건) | 0.4286 (63건) | 0 |
| 실패 클릭 회피율 | 0.8182 (11건) | 0.8182 (11건) | 0 |
| test split exact | 11 / 19 | 11 / 19 | 0 |
| 위험 행동 자동 클릭 | 0건 | 0건 | 0 |

목표별 exact/positive도 양쪽이 같다.

| goal_id | exact / positive |
|---|---:|
| `account.delete` | 8 / 18 |
| `account.signup` | 2 / 8 |
| `membership.cancel` | 11 / 23 |
| `membership.change` | 3 / 11 |
| `membership.join` | 3 / 3 |

## 개선되지 않은 이유

v2는 RLDS Episode/Step, SKOS Goal, PROV evidence와 신뢰도 계층을 추가한다. 하지만 v1과 v2가 사용하는 선택 로직은 여전히 다음 정보가 중심이다.

- 과거에 선택된 후보의 label·기능 role
- 화면 의미 유사도
- 목적별 role prior
- 성공·실패 outcome

2026-08-03 후보 복구에서 74개 step의 전체 후보 1,537개를 원본과 1:1로 복구했지만, 이 정보는 현재 `interaction-episode` JSONL에만 있고 runtime Retriever의 후보 점수에는 아직 연결되지 않았다. 즉, v2는 데이터 규격은 좋아졌지만 “왜 선택 후보가 같은 화면의 다른 후보보다 나았는가”를 사용하지 않는다.

## 구조 수정 결정

다음 변경 전까지 데이터 확대를 중단한다.

1. complete candidate inventory를 DB-native `experience_step_candidates` 계층으로 적재한다.
2. 과거 선택 후보와 같은 화면의 경쟁 후보를 함께 검색한다.
3. 미선택 후보를 무조건 실패로 취급하지 않고 pairwise preference context로 사용한다.
4. source app을 제외한 상태에서 선택 후보가 경쟁 후보보다 높게 평가되는지 측정한다.
5. 같은 74개 화면에서 다시 A/B하고 첫 행동과 전체 다음 행동이 개선될 때만 실기기 단계로 넘어간다.

이번 결과는 목적지 도달률이나 연속 경로 성공률을 증명하지 않는다. 오프라인 단일-step 진단에서조차 개선이 없었으므로 현재 상태를 성공으로 판정하지 않는다.
