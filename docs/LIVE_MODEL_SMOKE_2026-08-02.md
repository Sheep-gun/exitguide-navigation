# 실모델 Navigation smoke 결과 — 2026-08-02

> 이 문서의 K-EXAONE 측정은 교체 전 병목 분석 기록이다. 현재 두뇌 모델은 Solar Pro 3다.

## 구성

- 기억: N100 canonical Navigation Decision DB의 읽기 전용 로컬 복사본
- 눈: A100 `EXAONE-4.5-33B`, SSH loopback tunnel
- 두뇌: 기존 작업물의 K-EXAONE endpoint와 비밀 환경변수
- 입력: 개인정보가 없는 합성 Account 화면(`Profile`, `Settings`, `Membership`)
- 목적: `회원 탈퇴 메뉴를 찾고 싶어`

비밀값, 모델 응답 원문, 실제 휴대폰 스크린샷은 결과 파일과 Git에 저장하지 않았다.

## 측정 결과

| 검사 | 결과 | 지연 |
|---|---|---:|
| EXAONE 4.5 후보 ID 보존 | 성공, 3/3 유지 | 4.462초 |
| K 계획 1회 + 단일 후보 검증 1회 | 구조화 응답 성공 | 106.709초 |
| 최초 API: 별도 계획 + 후보별/일괄 평가 | 후보 ID·안전 계약 성공 | 106.495초 |
| 계획+전체 후보평가 단일 Hermes 호출 | 구조화 응답 성공 | 92.037초 |
| selective, VLM 생략 | 구조화 응답 성공 | 68.084초 |
| 중간 허브 강조 + 유일 best 강제 | 무정보/불일치 응답 거부, HTTP 503 | 56.740초 |

## 발견한 실패

처음 K-EXAONE 응답은 `Profile`, `Settings`, `Membership` 모두를 “회원탈퇴 그 자체가
아니다”라는 이유로 0점 처리했다. 기존 정렬은 동률에서 문자열 순서로 `membership`을
선택했다. 이는 API 계약은 지켰지만 목적상 잘못된 첫 행동이다.

수정 후에는 다음 조건을 강제한다.

- 직접 목적지가 아니어도 유용한 중간 허브면 높은 값을 줄 것
- 모든 허용 행동에 정확히 한 점수
- 유일한 `best_action_key`
- 최고 점수 0.5 이상, 2위와 0.02 이상 간격
- best key와 실제 최고 점수 일치
- 위 조건 실패 시 임의 클릭 금지

강화 후 실모델은 유효 순위를 내지 못했고 API가 503으로 실패 폐쇄했다. 잘못된 클릭은
막았지만 첫 행동 성공률 개선은 달성하지 못했다.

## 결론

- A100 VLM 연결과 의미 후보 보강 경로는 작동한다.
- K-EXAONE의 현재 endpoint는 왕복 지연과 다단계 중간 허브 가치 평가가 병목이다.
- 현재 신규 구조가 기존 DB 방식보다 낫다고 결론 내릴 수 없다.
- 정적 데이터를 더 쌓지 않는다.
- 다음 수정 우선순위는 (1) K 출력 계약을 더 작은 랭킹 표현으로 바꾼 비교 실험,
  (2) VLM 기능-role 보강 후 DB-only 선택 정확도 측정, (3) 앱 분리 오프라인 A/B다.
- 실기기 검증은 N100↔A100 지속형 인증 터널과 위 오프라인 게이트를 통과한 뒤 진행한다.

## Solar Pro 3 교체 검증

동일한 N100에서 Upstage OpenAI-compatible endpoint와 `solar-pro3` 모델을 확인했다. 비밀키는
`/srv/exitguide/secrets/navigation-planner.env`에만 두고 저장소와 결과 파일에는 기록하지 않았다.

| 검사 | 결과 | 지연 |
|---|---|---:|
| `Reply only with OK` 단순 completion | HTTP 200, 실제 응답 모델 `solar-pro3-260323` | 0.499초 |
| 강제 OpenAI/Hermes tool call | HTTP 200, 함수명·arguments 보존 | 0.594초 |
| Navigation 계획+전체 후보 평가 | HTTP 200, `settings` 선택, 후보 ID 계약 보존 | 4.212~6.166초 |
| DB 고신뢰 fast path | HTTP 200, 모델 호출 없이 `signup` 선택 | 0.018초 |
| 위험 최종 행동 경계 | HTTP 200, 해지 확정 클릭 없이 `stop_for_user()` | 0.024초 |
| 정상 history가 있는 2단계 DB fast path | HTTP 200, Solar 미호출 | 0.021초 |
| 관찰된 `no_change` 이후 선택적 escalation | HTTP 200, Solar 호출 | 4.520초 |

이는 endpoint·구조화 호출·런타임 안전 경계 검증이다. 첫 합성 화면에서 후보 선택은 합리적이었지만,
범용 정확도와 기존 방식 대비 개선 여부는 앱 분리 A/B로 별도 판정한다.
