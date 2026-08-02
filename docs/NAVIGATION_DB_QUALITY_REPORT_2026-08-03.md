# Navigation DB 표준화·품질 보고서

## 결론

**스키마와 무손실 변환은 준비됐지만, 현재 데이터는 범용 성능을 주장하기에 부족하다.**

- SQLite 구조 검증: 전 항목 통과
- 원본 v1 SHA-256 보존: 통과
- 앱 split 누수: 0건
- 위험한 최종 행동 클릭: 0건
- JSON Schema 오류: 0건
- 결론 코드: `schema_ready_data_not_generalization_ready`

## 현재 수량

| 계층 | 수량 |
|---|---:|
| Goal / phrase / relation | 6 / 41 / 4 |
| Destination Signature | 6 |
| Semantic screen / observation | 73 / 73 |
| Affordance | 1,525 |
| RLDS-compatible Episode / Step | 25 / 74 |
| Transition / Recovery | 74 / 11 |
| Evidence / PROV mapping | 222 / 222 |
| Provenance Activity | 137 |
| 평가 split 앱 | 8 |

DB 크기는 v1 `1,912,832 bytes`에서 표준 profile을 포함한 v2 `2,310,144 bytes`가 됐다.
원본 데이터의 의미를 늘린 것이 아니라 표준 매핑과 검증 가능한 관계를 추가한 증가다.

## 출처별 사용 가능 경험

| 출처 | Episodes | Steps |
|---|---:|---:|
| Human Gold | 14 | 63 |
| 실기기 실패 기록 | 11 | 11 |

원본에는 Human Gold recording 21개, 92 Step이 실제로 있다. 현재 핵심 범위에 들어온 것은
14개 recording, 63 Step이다. 제외된 7개, 29 Step은 `notification.settings` 5개/22 Step과
`marketing.settings` 2개/7 Step이다. 데이터가 사라진 것이 아니라 현재 범위 밖이라 원본에만
보존된 것이다.

## 목표별 범위

| goal_id | Episodes | Steps | Apps | 판단 |
|---|---:|---:|---:|---|
| `account.delete` | 4 | 18 | 4 | 소규모 오프라인 평가 가능 |
| `account.signup` | 3 | 8 | 3 | 소규모 오프라인 평가 가능 |
| `membership.cancel` | 15 | 34 | 6 | 현재 가장 많은 근거 |
| `membership.change` | 2 | 11 | 2 | 경계선 |
| `membership.join` | 1 | 3 | 1 | 범용 근거 부족 |
| `membership.manage` | 0 | 0 | 0 | 검증 사례 없음 |

## 확인된 부족분

- `membership.join`은 한 앱뿐이므로 일반화 근거로 사용할 수 없다.
- `membership.manage`는 검증된 decision episode가 없다.
- 현재 73개 화면에 EXAONE 4.5 VLM 관찰이 없고 Accessibility/OCR만 있다.
- Human Gold 21개 중 현재 범위에 들어온 것은 14개이며 나머지는 알림·마케팅 설정이다.
- 이번 검사는 first-action accuracy나 목적지 도달률을 측정하지 않았다.

## 다음 데이터 작업 조건

지금 정적 데이터를 추가하지 않는다. 먼저 앱 완전 분리 오프라인 A/B에서 기존 v1 Retriever와
표준화 v2 Retriever가 같은 74 Step을 동일하게 읽는지 확인한다. 그 다음 `membership.manage`,
`membership.join`, VLM 화면 관찰처럼 명확히 비어 있는 항목만 실기기에서 수집한다.
