# 계정 상태 보강 Runtime·Review 세대 전환

## 결과

55셀 동결 원료를 더 이상 운영 쓰기 대상으로 사용하지 않고, 계정 상태 보강 전용의 빈
Runtime·Review 세대로 Navigation API 쓰기 대상을 전환했다. Decision DB, Planner,
공개 Prior와 Android Executor 구현은 변경하지 않았다.

- generation: `account-state-recollection-v1`
- generation path: `/srv/exitguide/runtime/navigation-collection-generations/account-state-recollection-v1`
- creator commit: `33f49a9c82892d64876955655e0cde959bc6d9f9`
- activation script commits: `043c7d06330fc2cb60fa5b944e394fa2aa4cdb42`, `b5f5478842b9b7a380a28a0c3dbffff43b438929`
- base snapshot: `training_snapshot_d983e65055f5427fdb8d3dbe`
- activation receipt: `/srv/exitguide/runtime/navigation-collection-generations/account-state-recollection-v1/activation-receipt.json`
- activated_at: `20260806T120807Z`

## 이전 세대 봉인

- Runtime source: `/srv/exitguide/runtime/navigation-runtime-coverage-b-v2-ae3b7e0a.sqlite`
- Runtime SHA-256: `7af6bd7b765d79c1c0a14f415765f651878b578f89f2fd62b1538caf63ffc4ea`
- Review source: `/srv/exitguide/runtime/navigation-human-review-v1.sqlite`
- Review SHA-256: `8ad8e3687188a4b340817f5e9fa6489b6baf2175245d23d3172afb48097a4c3a`
- source permissions after rollover: `0440`
- active sessions before stop: 0
- archive: `/srv/exitguide/runtime/collection-generations/frozen-20260806T120807Z`
- archive Runtime SHA-256: `34fba75c28ffcdea1d7537d9f47c029cbd1041a80023c6e6d8c6662c35697a10`
- archive Review SHA-256: `66a81b67686955d89d6e4f677c224a32f1fc19e8fb75b6d2fddd60420dd8ac23`
- archive Runtime: 265 sessions, 1,439 decisions, quick_check ok
- archive Review: 300 reviews, 5,593 candidate labels, quick_check ok

보관본은 `0440` 파일과 `0550` 디렉터리로 유지한다. WAL 생성이 필요한 일반 모드가 아니라
SQLite `immutable=1` 읽기 전용 모드로 무결성을 검증한다.

첫 시도 `20260806T120713Z`는 systemd 시작 직후 health 요청을 보내 연결이 아직 열리기 전에
실패했다. 스크립트가 기존 환경 파일을 복구하고 서비스를 재시작했으며 기존 DB 해시와 권한을
재확인했다. 이후 최대 30초 readiness 대기를 추가해 재실행했다. 첫 시도의 보관 복사본은
삭제하지 않고 롤백 감사 자료로 보존한다.

## 새 세대

- Runtime: `navigation-runtime-v1.sqlite`, schema v5
- Review: `navigation-human-review-v1.sqlite`, schema v2
- Runtime/Review 파일 분리: true
- API 확인 Runtime counts: sessions 0, decisions 0, observations 0
- API 확인 Review counts: reviewed 0, remaining 0
- API `/health`: 200, status ok
- API `/v1/navigation/status`: ready true
- Review source_read_only: true
- 기존 Decision DB 접근: read-only 유지
- 공개 Prior: enabled, planner advisory only
- 위험 행동 자동 실행: 0

실기기 `R3CR60V3DKM`은 ADB `device`이며 reverse는
`tcp:8100 → tcp:18104`로 유지됐다. 계정 상태를 사용자가 준비하기 전까지 수집은 paused다.

