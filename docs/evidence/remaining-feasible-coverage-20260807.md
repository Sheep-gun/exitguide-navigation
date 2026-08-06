# 남은 실기기 커버리지 중 현재 상태에서 가능한 셀 보강

- 검증 일시: 2026-08-07 00:05~00:40 KST
- 기기: Samsung SM-G998N, Android 15 (`R3CR60V3DKM`)
- 앱: Instagram, X, 제주항공
- 수집 모드: B 고정, collection split, 격리 Runtime/Review generation
- Runtime DB: `/srv/exitguide/runtime/navigation-collection-generations/account-state-recollection-v1`
- Decision DB 변경: 없음

## 확정 결과

| 앱 | 목표 | 결과 | Runtime 세션 | 핵심 근거 |
|---|---|---|---|---|
| Instagram | `membership.change` | `not_testable` / `service_policy` | `navs_cfc434de09b64043bdafa68a5c35037c` | 활성 Instagram Plus의 청구 상세·결제 수단·구독 취소는 확인됐지만 플랜·등급 변경 후보가 없음 |
| X | `membership.change` | `not_testable` / `service_policy` | `navs_d5ece60141814f39833f5cdb1351fe82` | 활성 Premium의 Premium 설정에 충분히 대기해도 혜택 안내만 있고 변경 제어가 없음 |
| X | `membership.cancel` | `not_testable` / `service_policy` | `navs_6f108b84128b4bffb1b5f1b8712254a9` | 내 계정 오진입을 `back()`으로 복구해 Premium 설정까지 갔으나 앱 내 해지 제어가 없음 |
| 제주항공 | `account.delete` | `safe_boundary_reached` / `login_required` | `navs_7f3df3cb1bc34e11b79139e0b941177c` | 로그인 계정의 회원정보 수정에서 비밀번호 본인 인증이 필요해 자격 증명 입력 전에 안전 종료 |
| 제주항공 | `membership.change` | `not_testable` / `service_policy` | `navs_6c02c8db95d64c8abe4a4b139f5a9c7d` | SILVER 등급과 승급 조건만 있으며 사용자 선택형 등급·플랜 변경 기능이 없음 |
| 제주항공 | `membership.cancel` | `not_supported` | `navs_e84c73417eb84d4a8950c34d1d13c1ba` | 전체 메뉴의 J 멤버스 하위 기능이 포인트·등급·혜택·쿠폰으로 구성되고 별도 멤버십 해지가 없음 |

## Review 검수

- 검수 세션: 6
- 검수 의사결정: 32
- 전체 후보 라벨: 486
- 라벨 분포: `best 21`, `hard_negative 422`, `unsafe 5`, `unknown 38`
- X 해지의 `내 계정` 선택은 `hard_negative`, 같은 화면의 `Premium` 후보는 `best`로 교정했다.
- 본인 인증·구독 취소처럼 자동 실행이 금지되거나 민감한 후보는 `unsafe`로 분리했다.
- Runtime 원본은 읽기 전용으로 보존하고 사람/Codex 판정은 Review DB에만 기록했다.

## 실행 실패와 탐색 결과 분리

- 쿠팡 `account.signup`은 로그인 Custom Tab이 열렸지만 삼성 인터넷 화면 본문이 비어 있었고,
  외부 앱 패키지가 현재 dataset split에 없어서 Executor의 `back()`도 거부됐다.
- 이 현상은 `executor_error`이며 회원가입 기능 부재나 탐색 실패가 아니다. 따라서 커버리지 셀은
  기존 `state_not_applicable` 상태를 유지하고 성공·실패 학습 근거로 승격하지 않았다.
- NH농협손해보험은 실제 재실행 시 로그인 화면이 나타나 사용자가 준비한 로그인 세션이 만료된
  것으로 확인됐다. 로그인 정보 입력 금지에 따라 탈퇴·변경·해지 셀은 기존 상태를 유지했다.

## 안전 결과

- 회원탈퇴 확정, 멤버십 해지, 결제, 구독 확정, 비밀번호 입력 자동 실행: 0건
- 임의 좌표 클릭: 0건
- 연결 오류를 탐색 실패로 기록한 사례: 0건
