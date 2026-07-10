# ExitGuide 통합 계약 v1

Navigation과 Terms는 독립적으로 개발하고 최종 앱에서 결합한다. 이 문서는 Navigation 저장소가 보장하는 최소 API 계약이다.

## Navigation 요청

```http
POST /v1/navigation/guide
Content-Type: application/json
```

```json
{
  "request_id": "req_123",
  "app_package": "com.example.app",
  "app_version": "1.0.0",
  "platform": "android",
  "locale": "ko-KR",
  "goal_id": "cancel_subscription",
  "goal_text": "구독을 해지하고 싶어",
  "session": {
    "last_confirmed_state_id": "membership_home",
    "failed_element_ids": [],
    "failed_candidate_meanings": [],
    "retry_count": 0
  },
  "screen_elements": [
    {
      "id": "node_12",
      "text": "멤버십 관리",
      "content_description": null,
      "view_id": "com.example.app:id/manage_membership",
      "role": "button",
      "clickable": true,
      "bounds": [120, 530, 960, 610]
    }
  ]
}
```

## Navigation 응답

```json
{
  "request_id": "req_123",
  "route_id": "example_android_cancel_subscription_ko_v1",
  "route_version": 1,
  "current_step": 2,
  "current_state_id": "membership_management",
  "target_element_id": "node_12",
  "instruction": "멤버십 관리를 누르세요.",
  "warning": null,
  "requires_user_confirmation": false,
  "confidence": 0.94,
  "navigation_state": "on_route",
  "recovery": null,
  "source_files": [
    "example_android_cancel_subscription_ko_v1.md"
  ],
  "status": "guided"
}
```

## 상태 값

```text
guided          안내 가능한 현재 단계
reanchored      다른 단계 또는 경로 변형에서 현재 화면을 다시 찾음
recovery_required 안전한 사용자 복귀 행동이 필요함
needs_review     후보는 있지만 확신도가 낮음
route_not_found  해당 앱·목적 경로가 없음
goal_completed   목표 달성 화면이 확인됨
```

## 경로 복구 응답

현재 화면을 검증 경로에 매칭할 수 없고 뒤로 가기가 안전할 때는 `target_element_id` 대신 복구 지시를 반환한다.

```json
{
  "request_id": "req_124",
  "route_id": "example_android_cancel_subscription_ko_v1",
  "current_state_id": null,
  "target_element_id": null,
  "instruction": "현재 화면은 확인된 경로와 다릅니다. 이전 화면으로 한 번 돌아가 주세요.",
  "warning": null,
  "requires_user_confirmation": true,
  "confidence": 0.41,
  "navigation_state": "recovery_required",
  "recovery": {
    "type": "back",
    "safe": true,
    "expected_previous_state_id": "membership_home",
    "retry_after_recovery": true
  },
  "status": "guided"
}
```

## Terms 서비스와의 결합

Navigation은 약관 내용을 직접 해석하지 않는다. 현재 화면이 약관·결제·환불 안내로 판단되면 최종 통합 백엔드가 군협의 Terms API를 별도로 호출한다.

```text
Navigation API 결과
├─ 다음 UI 요소
├─ 목적 방해 경고
└─ 최종 확인 여부

Terms API 결과
├─ 관련 조항 요약
├─ 사용자 목적과의 충돌
└─ 동의·미동의 판단 근거
```

최종 앱은 `request_id`, `app_package`, `goal_id`를 공통 연결 키로 사용한다.

## 변경 규칙

- 필드 삭제나 의미 변경은 v2 계약에서만 수행한다.
- v1에는 선택 필드를 추가할 수 있다.
- `goal_id` 목록은 두 저장소에서 동일하게 유지한다.
- `target_element_id`는 반드시 요청의 `screen_elements[].id` 중 하나이거나 `null`이어야 한다.
- `requires_user_confirmation=true`인 결과는 자동 실행하지 않는다.
- `failed_element_ids`에 포함된 요소는 같은 세션에서 다시 안내하지 않는다.
- 대체 후보는 동일한 마지막 확인 화면에 존재하고 예상 다음 상태가 정의된 안전한 요소여야 한다.
- `recovery.safe=false`인 단계에서는 일반적인 뒤로 가기를 요청하지 않는다.
- 기본 최대 시도 횟수는 첫 후보와 대체 후보를 합쳐 2회다.
- 최대 시도를 넘으면 `needs_review`를 반환하고 추가 후보를 추측하지 않는다.
