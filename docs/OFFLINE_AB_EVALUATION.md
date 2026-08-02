# 오프라인 평가 보고서 — 2026-08-02

## 평가 계약

```powershell
.\.venv\Scripts\python.exe scripts\Evaluate-NavigationRuntimeOffline.py `
  --db .artifacts\integration\navigation-decision-v1.sqlite `
  --output .artifacts\integration\offline-diagnostic-final.json
```

- 사례 수: 74
- 검색 시 해당 사례의 source app 완전 제외
- 앱 split: train 42, validation 13, test 19
- 모델 endpoint 미사용, decision-memory fallback 진단
- Human Gold 좌표나 앱별 클릭 배열 재생 없음

## 결과

| 지표 | 결과 |
|---|---:|
| 목적 정규화율 | 1.0000 |
| 첫 행동 정확도 | 0.7778 (9건) |
| 전체 positive next-action exact match | 0.4603 (63건) |
| 기록된 실패 클릭 회피율 | 0.8182 (11건) |
| 위험 행동 자동 클릭 | 0건 |

Holdout `test` split은 positive 19건 중 11건 exact match였다. 목표별 exact/positive는
회원탈퇴 8/18, 회원가입 2/8, 멤버십 해지 13/23, 멤버십 변경 3/11, 멤버십 가입
3/3이다.

## A/B 완료 여부

이 결과는 A/B가 아니다. 같은 화면 집합에서 기존 DB runtime을 같은 API·안전 정책으로
실행한 baseline 수치가 현재 clean redesign 저장소에 없다. 따라서 다음은 말할 수 없다.

- 신규 DB가 기존 DB보다 첫 행동 정확도가 높다.
- 신규 DB가 전체 목적지 도달률을 개선했다.
- 처음 보는 앱 성공률이나 UI 변경 복구율이 개선됐다.

현재 next-action exact 46.03%만으로 데이터 확대를 승인하지 않는다. 기존 baseline adapter를
별도 읽기 전용으로 복구해 동일 후보·동일 앱 split에서 비교하거나, 실기기 연속 경로 성공률을
수집하기 전까지 “개선됨” 결론은 보류한다.

## 다음 게이트

1. 기존 DB baseline adapter를 매크로 재생 없이 동일 `DecideRequest` 계약으로 연결
2. 앱 단위 고정 split에서 baseline/new 동시 실행
3. 첫 행동·전체 행동·목적지 도달·오클릭·복구·시간을 동일 세션으로 측정
4. 개선이 없으면 데이터 추가 대신 goal decomposition과 중간 허브 가치 계약 수정
