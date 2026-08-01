# 목적지 탐색 시간 최적화

ExitGuide는 `Time to Confirmed Destination(TCD)`을 사용해 기능 그래프 경로를 개선한다. TCD는 사용자가 플로팅 시작 버튼을 누른 시점부터 앱이 최종 목적 버튼을 확인해 표시한 시점까지다. 해지·삭제·결제 같은 최종 버튼을 사용자가 실제로 누르는 시간은 포함하지 않는다.

## 최적화 순서

속도는 정확도와 안전성의 대체 지표가 아니다. 경로 선택은 다음 순서를 지키는 사전식(lexicographic) 정렬이다.

1. 검증된 최종 목적지 정확도
2. 최종 상태 변경 버튼 앞 안전 정지와 위험 자동 클릭 0건
3. 현재 앱 버전에서의 반복 성공률과 최소 표본 수
4. 외부 앱 대기를 제외한 제어 가능 시간 p90·p50, 그다음 원본 TCD p90·p50
5. 클릭·스크롤·뒤로 가기 비용
6. 최근 성공 시각

빠르지만 오답이거나 위험한 경로는 시간 비교 대상에서 제외된다. 앱 네트워크 지연은 원본 TCD에는 포함하되 `controllable_time_ms`에서는 제외하므로, 느린 인터넷 한 번만으로 의미상 올바른 경로가 과도하게 강등되지 않는다. 3회 미만의 신규 경로는 `under_sampled`로 남겨 탐색 후보를 잃지 않으며, 검증된 경로가 여러 개이면 10회 중 1회 결정론적으로 예비 경로를 확인한다. 최적·예비 2·3순위는 `route_rankings`에 함께 남는다.

## 계측 구간

`POST /v1/navigation/agent/observe` 요청과 응답의 timing 계약은 다음 구간을 구분한다.

- `server_total_ms`: API가 관찰 요청을 처리한 전체 시간
- `model_decision_ms`: K-EXAONE 호출 시간. 결정론적 경로는 0일 수 있다.
- `db_lookup_ms`: 화면·그래프·캐시 조회 시간
- `screen_analysis_ms`: 접근성 구조를 후보로 정규화한 서버 시간
- `screen_capture_ms`: 단말 스크린샷과 온디바이스 OCR 시간
- `action_execution_ms`: 자동 클릭·스크롤·뒤로 가기 명령 시간
- `ui_settle_ms`: 다음 화면 접근성 이벤트를 기다리는 안정화 시간
- `external_wait_ms`: 앱 네트워크·렌더링 등 나머지 외부 대기 시간
- `time_to_confirmed_destination_ms`: 전체 TCD. 목적지 확정 응답에서만 값이 생긴다.

Android는 시작 버튼에서 생성한 `startNonce` 시각을 사용해 TCD를 계산한다. 서버 하위 시간은 `server_total_ms` 안에 포함되므로 합산할 때 모델·DB·화면 분석 시간을 다시 더하지 않는다. 앱 로딩이 느린 경우 `external_wait_ms`로 분리되어 경로 자체의 의미 점수를 과도하게 떨어뜨리지 않는다.

목적지 응답이 실제 오버레이에 전달된 직후 APK는 `POST /v1/navigation/agent/performance/complete`로 최종 단말 TCD를 확인한다. 따라서 요청 직전의 중간 경과시간이 아니라 마지막 API 왕복과 결과 표시까지 포함한 값이 성능 DB의 권위 있는 실기 수치가 된다. 이 보정 전 응답의 TCD는 진행 상태 표시용 추정치다.

## SQLite 구조

기존 `.artifacts/universal-navigation.sqlite`에 다음 성능 계층이 추가된다.

| 테이블 | 역할 |
|---|---|
| `navigation_sessions` | 앱·버전·목적별 전체 TCD, 성공·안전·상호작용·복구 통계 |
| `navigation_stage_timings` | 화면 단계별 서버·모델·DB·OCR·조작·대기 시간 |
| `graph_edge_performance` | 기능 그래프 간선의 성공·실패와 평균·p50·p90 추정 이동 시간 |
| `route_performance` | 경로별 정확도·안전 정지·오클릭·TCD·상호작용 비용 |
| `app_version_signatures` | 패키지·버전·locale 경계와 유효·무효 경로 수 |
| `route_rankings` | 안전 기준을 통과한 최적·예비 경로 순위와 제한 탐색 상태 |

앱 버전은 `app_key`와 `version_signature`에 포함된다. 새 버전은 이전 경로를 무조건 실행하지 않고 콜드 탐색으로 시작한다. 현재 버전에서 다시 성공한 경로만 해당 버전 순위에 들어간다.

화면 원문과 사용자 목적 원문은 성능 테이블에 저장하지 않는다. 목적은 SHA-256 기반 `goal_key`, 화면은 개인정보를 제거한 구조 fingerprint로만 연결한다.

## Gym과 실기 수치의 경계

Navigation DB Gym은 콜드 단계당 1,200ms, 웜 단계당 450ms의 명시된 합성 비용 모델로 경로 재사용 정책을 회귀 검증한다. 이 값은 `measurement_source=synthetic`이며 실제 휴대전화 성능 주장이 아니다.

```powershell
.\scripts\Run-NavigationDbGym.ps1 -Mode fast -Gate
.\scripts\Run-NavigationDbGym.ps1 -Mode full -GeneratedVariants 3 -Gate
```

보고서에는 정확도·안전 지표와 함께 TCD p50·p90, 판단 p50·p90, 10·30·60초 내 성공률, 콜드/웜 p50, 캐시 시간 단축률, 앱·목적별 최단 성공 경로가 기록된다. 이전 JSON 보고서를 `-Baseline`으로 넘기면 공통 지표 변화도 계산한다.

실제 기기 수치는 `real_device` 또는 사람이 정답을 확인한 `real_device_gold`만 사용한다. 예시 파일은 `fixtures/navigation/db-gym/real-device-performance.example.json`이다.

```powershell
.\scripts\Import-NavigationPerformance.ps1 `
  -InputPath .\device-performance.json `
  -CheckOnly

.\scripts\Import-NavigationPerformance.ps1 `
  -InputPath .\device-performance.json
```

가져오기는 `goal_text`, 화면 원문, 이름, 이메일, 전화번호, 비밀번호, 토큰, 결제정보가 있으면 중단된다. `-CheckOnly`로 개인정보·스키마 검사를 통과한 뒤 실제 DB에 넣는다.

현재 실기 집계는 다음 API로 확인한다.

```http
GET /v1/navigation/agent/performance?measurement_source=real_device
```

## K-EXAONE 경계

K-EXAONE은 목적을 기능 ID로 해석하거나 의미가 비슷한 현재 화면 후보를 재정렬하고 실패 원인의 검토 후보를 만들 수 있다. 모델이 기대 정답, 성공 여부, TCD를 생성하거나 DB 순위를 직접 변경하지 않는다. 제안은 계속 `review_required=true`, `auto_apply=false` 상태로만 저장한다.
