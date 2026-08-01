---
route_id: egl_stream_android_cancel_subscription_ko_v1
app: EGL Stream (synthetic)
package: lab.exitguide.stream.demo
platform: android
locale: ko-KR
goal: cancel_subscription
route_version: 1
status: demo_verified
verified_at: 2026-07-10
verified_by: ExitGuideLab
---

# EGL Stream — 구독 해지 모범 경로

실제 서비스 경로라고 주장하지 않는 통합 MVP용 합성 경로다. 좌표가 아니라 화면 대표 문구와 버튼 의미를 기준으로 현재 단계를 다시 찾는다.

1. 계정 메뉴에서 `구매 항목 및 멤버십`을 선택한다.
2. 구매 항목 및 멤버십에서 `Premium 멤버십`을 선택한다.
3. 멤버십 관리에서 `비활성화`를 선택한다.
4. 일시중지 제안에서 `계속 해지`를 선택한다.
5. 종료일과 다음 결제 여부를 확인한 뒤 `Premium 해지`를 사용자가 직접 선택한다.
6. `해지 완료`와 `다음 결제 없음`을 확인한다.

## 복구 규칙

- 알려진 다른 단계가 보이면 그 단계로 경로를 재정렬한다.
- 알 수 없는 안전한 화면에서는 사용자가 뒤로 가기를 한 번 누르도록 요청한다.
- 실패한 요소는 같은 세션에서 다시 추천하지 않는다.
- 두 후보가 실패하면 더 추측하지 않고 검수 필요 상태로 끝낸다.

## 약관 연결

최종 확인 화면에서는 Terms 검색에 `구독 해지 자동 갱신 다음 결제`를 전달한다. Navigation은 버튼 안내만 결정하고, 약관 근거는 기존 Terms corpus에서 별도로 가져온다.
