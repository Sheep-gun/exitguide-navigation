# 계정 상태별 골든 라벨 보강 계획

기존 55셀 Runtime·Review와 `training_snapshot_d983e65055f5427fdb8d3dbe`는 수정하지
않는다. 사용자가 다른 계정 상태를 준비하면 새로운 Runtime 세션과 Review 라벨을 append-only로
추가하고, 이후 새로운 불변 스냅샷 세대로 동결한다.

## 우선 완료해야 할 3셀

| 앱 | 목표 | 필요한 상태 |
|---|---|---|
| YouTube | 멤버십 변경 | 대체 요금제·업그레이드·다운그레이드·가족 플랜 중 하나가 노출되는 활성 Premium 계정 |
| Netflix | 멤버십 변경 | 계정 페이지에 `멤버십 변경` 또는 동등한 플랜 선택이 노출되는 계정 소유자 프로필 |
| 포스타입 | 멤버십 변경 | 변경 가능한 다른 등급이 존재하는 활성 크리에이터 멤버십 |

YouTube 회원가입은 기존 실기기 근거가 이미 기기 본인 인증 프롬프트까지 도달하고
`stop_for_user()`로 종료했으므로 `safe_boundary_reached`로 교정했다. 새 수집은 필요 없다.

## 높은 가치의 추가 보강

1. 멤버십 미가입 계정으로 YouTube·Netflix·배달의민족 `membership.join`
2. 활성 구독 계정으로 현재 `state_not_applicable`인 `membership.change`·`membership.cancel`
3. 로그아웃 상태로 현재 로그인 중인 앱의 `account.signup`
4. 로그인 상태로 제주항공·NH농협손해보험 `account.delete`

## 사용자와 Executor의 역할

- 사용자가 로그인·로그아웃, 계정 선택, 구독 상태 준비를 직접 수행한다.
- 비밀번호, 생체 인증, 결제 정보는 Runtime·Review에 수집하지 않는다.
- Executor는 상태 준비가 끝난 화면부터 candidate_id 기반 안전 탐색만 실행한다.
- 결제·가입·변경·해지·탈퇴 확정 직전에는 `stop_for_user()`로 종료한다.
- 연결 오류는 탐색 실패로 기록하지 않는다.
- 기존 판정과 스냅샷을 덮어쓰지 않고 새 세대가 이전 세대를 supersede하도록 기록한다.

기계 판독 계획은 `db/navigation_account_state_recollection_v1.json`이다.

