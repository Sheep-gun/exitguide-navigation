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
  "target_element_id": "node_12",
  "instruction": "멤버십 관리를 누르세요.",
  "warning": null,
  "requires_user_confirmation": false,
  "confidence": 0.94,
  "source_files": [
    "example_android_cancel_subscription_ko_v1.md"
  ],
  "status": "guided"
}
```

## 상태 값

```text
guided          안내 가능한 현재 단계
needs_review     후보는 있지만 확신도가 낮음
route_not_found  해당 앱·목적 경로가 없음
goal_completed   목표 달성 화면이 확인됨
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
