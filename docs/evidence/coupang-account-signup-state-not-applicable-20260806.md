# 쿠팡 account.signup 현재 계정 상태 실기기 근거

검증 일시: 2026-08-06 17:48~17:53 (Asia/Seoul)

## 결론

쿠팡 앱은 현재 로그인 상태다. 별도 `account.signup` 세션에서 홈의 `마이쿠팡`을
candidate_id로 실행해 개인화된 계정명과 주문·결제·설정 영역을 관찰했다. 로그아웃이나
계정 상태 변경 없이 `state_not_applicable`로 종료했다.

## Runtime 원료

- goal_id: `account.signup`
- Runtime session: `navs_fd03f9553d904949a47a7414c6c997aa`
- step 0: `navd_e34a8c3218aa4268b912348fa868924e`
- step 1: `navd_89a280b8a75b463fab6a4954631eb42d`
- 실행 경로: 쿠팡 홈 -> `마이쿠팡`
- 관찰 근거: 마스킹된 개인화 계정명, 설정, 주문내역, 쿠페이 머니, 쿠팡 캐시
- 세션 상태: `stopped / safe_user_handoff`
- candidate set: complete
- 연결 오류: false
- 로그아웃·회원가입·계정 변경: 0건
- 위험 행동 자동 실행: 0건

## Review 골든 라벨

- 결정 검수: 2 / 2
- 전체 후보 라벨: 65 / 65
- 전체 분포: `best` 1, `hard_negative` 44, `unknown` 20
- 홈의 `마이쿠팡`: `best`
- 로그인 계정 화면의 후보: signup 진행 후보가 아니므로 `hard_negative` 또는 의미 부족 시 `unknown`
- 최종 `stop_for_user`: `correct / reached`
- Runtime의 `blocked / unknown`: 현재 로그인 상태 판정 성공을 표현하지 못해 `incorrect`로 교정
- reviewer: `codex-yanggeon`
- label_source: `codex`
- review_status: `verified`
- Runtime 원본: 읽기 전용 보존

## 수집기 판정

후보 수집, candidate_id 실행, 화면 변화 관찰, Runtime 기록이 모두 정상이다. 이번 검증에서
수집기 코드는 수정하지 않았다.
