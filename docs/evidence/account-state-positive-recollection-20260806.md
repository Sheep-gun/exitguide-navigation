# 계정 상태 변경 후 긍정 경로 재수집 — 2026-08-06

## 범위

사용자가 준비한 새 계정·구독 상태에서 기존 `state_not_applicable` 셀을 다시 탐색했다. 격리된 `account-state-recollection-v1` Runtime/Review DB만 사용했으며 기존 Runtime DB, Decision DB, Gold와 AndroidControl 자료는 변경하지 않았다.

## 확정한 셀

| 앱 | 목표 | 실제 관찰 결과 | 안전 종료 |
|---|---|---|---|
| YouTube | `membership.join` | 내 페이지 → Premium 구매 → YouTube Premium 가입·무료 체험 화면 | 가입·결제 전 `stop_for_user` |
| Postype | `account.signup` | 회원 가입 → Google·Naver·이메일 인증 수단 | 인증·개인정보 입력 전 `stop_for_user` |
| ChatGPT | `account.signup` | 로그인 → 다른 방법으로 로그인 → 로그인 또는 회원 가입 화면 | 인증·개인정보 입력 전 `stop_for_user` |
| Instagram | `membership.cancel` | 프로필 → 옵션 → 계정 센터 → 구독 → Instagram Plus → 구독 취소 | 해지 실행 전 `stop_for_user` |
| Netflix | `membership.join` | 종료 예정 계정 홈 → 멤버십 재시작 | 구독 재시작 전 `stop_for_user` |
| 배달의민족 | `membership.join` | 마이배민 → 가입 배너 → 결제수단·약관·배민클럽 시작하기 | 가입·결제 전 `stop_for_user` |

## 검수

- Runtime 세션: 7개
- Review 검수 결정: 21개
- 전체 후보 라벨: 330개
- 클릭은 현재 화면에 존재하는 `candidate_id`만 사용했다.
- 선택 후보, 비선택 후보와 위험 후보를 모두 검수했다.
- 위험 행동 자동 실행: 0건
- 스크린샷 원본과 개인정보를 근거 문서에 저장하지 않았다.

## 성공으로 반영하지 않은 진단

- NH농협손해보험 `account.delete`: 로그인 후 MY → 마이페이지 → 개인정보조회/변경까지 식별했으나 해당 WebView 후보의 클릭이 실행되지 않았다. 탐색 성공이 아니라 Executor 실행 문제로 분리했다.
- X `membership.change`·`membership.cancel`: 활성 Premium 계정에서 Premium 설정 진입 후 충분히 기다렸으나 혜택 설명만 노출되고 변경·해지 후보가 나타나지 않았다. 서비스 제어 미노출 상태로 보존했다.
- 제주항공 `account.delete`: 시작 화면 후보 수집이 불완전하고 대기 후에도 화면이 바뀌지 않아 앱 로딩/실행 문제로 분리했다.

## Runtime 근거

- `runtime:navs_4402f1789d4d429c9dc9ae386a1141e7`
- `runtime:navs_fd6713cccec9458bb0fe83dcae00bdef`
- `runtime:navs_17775f2739874d47b8fc97c39a03b5cb`
- `runtime:navs_3731575d0ac648ca83c7730e606048f1`
- `runtime:navs_da541d3fcf0b441484192ba3bcc601ab`
- `runtime:navs_3de7a9b1ca814fb88835659f63972bf4`
- `runtime:navs_1cedff26697744fb89101d531e32cd29`
