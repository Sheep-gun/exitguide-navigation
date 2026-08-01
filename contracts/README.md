# ExitGuide Shared Contracts

이 디렉터리는 Terms와 Navigation이 함께 사용하는 최소 계약만 관리합니다. 각 모듈의 내부 구현과 전용 스키마는 담당 저장소에서 관리하고, 최종 앱이 두 결과를 조합하는 데 필요한 값만 여기서 고정합니다.

## 저장소 경계

| 모듈 | 담당 | 저장소 | 책임 |
| --- | --- | --- | --- |
| Terms + Integration | 김군협 | `exitguide-ai/exitguide` | 약관 수집, 검수, 검색, 근거 API, 최종 앱 조합 |
| Navigation | 양건 | `Sheep-gun/exitguide-navigation` | Android 화면 인식, 다음 UI 안내, 경로 이탈 복구 |

Navigation 저장소가 조직으로 이전되기 전까지는 현재 공개 저장소를 upstream으로 사용합니다. 코드를 이 저장소에 복사하지 않습니다.

## 공통 계약

- [`goals.v1.json`](goals.v1.json): 두 모듈이 공유하는 `goal_id` 목록
- Navigation API: [`exitguide-navigation/docs/INTEGRATION_CONTRACT.md`](https://github.com/Sheep-gun/exitguide-navigation/blob/main/docs/INTEGRATION_CONTRACT.md)
- Terms API: [`docs/API_CONTRACT.md`](../docs/API_CONTRACT.md)의 `/v1/terms-corpus*`

두 API는 `request_id`, `app_package`, `goal_id`를 공통 연결 키로 사용합니다. 현재 Terms 검색 API는 corpus 기준선 검증용이며, 화면 단위 통합 응답은 승인 corpus가 연결된 뒤 별도 v1 계약으로 추가합니다.

## 변경 규칙

1. `goal_id` 추가 또는 삭제는 `goals.v1.json`을 먼저 변경합니다.
2. Terms 백엔드의 목표 목록은 자동 검사에서 이 파일과 정확히 일치해야 합니다.
3. 기존 필드의 삭제나 의미 변경은 새 계약 버전에서만 수행합니다.
4. 한 모듈의 내부 provider, 데이터베이스, 모델 선택은 다른 모듈의 계약에 노출하지 않습니다.
5. 최종 앱은 Navigation과 Terms 중 하나가 실패해도 다른 결과를 표시할 수 있어야 합니다.
