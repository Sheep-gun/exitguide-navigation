# 제주항공 membership.change 현재 계정 상태 실기기 근거

검증 일시: 2026-08-06 17:26~17:32 (Asia/Seoul)

## 결론

제주항공 앱은 현재 로그아웃 상태다. 홈에서 `마이페이지`를 candidate_id로 실행하면
로그인 화면으로 이동하며, 변경할 활성 J 멤버스·멤버십을 관찰할 수 없다. 로그인이나
계정 상태 변경 없이 `state_not_applicable`로 종료했다.

## 정확한 목표 세션

- goal_id: `membership.change`
- Runtime session: `navs_f69fe038296340ae9f2db72aa54e27d7`
- decision: `navd_642ef19ef340443ea4c367b5217e3437`
- 실행 경로: 홈 -> `마이페이지`
- 실행 방식: Accessibility `candidate_id` 기반 클릭
- Runtime 결과: `login_required`, `observed_login_required`
- 세션 상태: `stopped / safe_user_handoff`
- 실행 성공: true
- 화면 변화: true
- 연결 오류: false
- 로그인 정보 입력: 0건
- 계정 상태 변경: 0건
- 위험 행동 자동 실행: 0건

## Review 골든 라벨

- 결정 검수: 1 / 1
- 전체 후보 라벨: 26 / 26
- 분포: `best` 1, `hard_negative` 19, `unknown` 6
- `마이페이지`: `best`
- 그 밖의 명시적 비목표 후보: `hard_negative`
- 의미가 없는 이름 없는 아이콘: `unknown`
- reviewer: `codex-yanggeon`
- label_source: `codex`
- review_status: `verified`
- Runtime 원본: 읽기 전용 보존

## 목표 정규화 교정 사례

첫 진단 문구 `J 멤버스 또는 멤버십 변경 메뉴까지 이동`은 Goal Ontology에서
`membership.manage`로 넓게 정규화됐다.

- 진단 session: `navs_4e7b1b687948422c869ea6fbad73ff86`
- 진단 decision: `navd_3c3f96b488d0410592abb3b860e81961`
- 후보 라벨: 26 / 26, verified

행동 원료 자체는 정상이라 보존·검수했지만 `membership.change` 셀의 완료 근거로 사용하지
않았다. 정확한 자연어 `멤버십 변경`으로 새 독립 세션을 실행해 표준 goal_id를 확인했다.

## 수집기 판정

후보 수집, candidate_id 실행, 화면 변화 관찰, Runtime 기록은 모두 정상이다. 이번 검증에서
수집기 코드는 수정하지 않았다. 첫 진단의 문제는 수집 실패가 아니라 목표 문구 정규화 범위였다.
