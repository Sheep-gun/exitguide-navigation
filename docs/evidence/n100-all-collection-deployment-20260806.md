# N100 11개 앱 collection 전환 배포 — 2026-08-06

## 결과

- Git commit: `0dee4c8557dd13961648a81f9f57ed5094eef6d1`
- API release: `/srv/exitguide/runtime/navigation-api-code-0dee4c8`
- active symlink: `/srv/exitguide/runtime/navigation-api-current-code`
- Runtime v2: `/srv/exitguide/runtime/navigation-runtime-coverage-b-v2-ae3b7e0a.sqlite`
- service: `exitguide-navigation-api.service`, `active`
- API: `ready=true`
- public prior: enabled, advisory-only
- split: collection 11, validation 0, locked_holdout 0
- manifest SHA-256: `ae3b7e0a0ea9f5fd392f173c33d005e43263aabba3c70ad37d40619662a620b0`

## Runtime 무손실 전환

운영 중이던 v1 Runtime을 직접 수정하지 않았다. SQLite `VACUUM INTO`로 일관성 있는
v2 복제본을 만든 뒤 복제본에서만 split을 전환했다.

| 항목 | v1 원본 | v2 운영 |
|---|---|---|
| sessions | 215 | 215 |
| decisions | 1,278 | 1,278 |
| observations | 1,225 | 1,225 |
| split | 7 collection / 1 validation / 3 locked holdout | 11 collection |
| SHA-256 | `f4a6d404f8385e396ad9f74f557acb32d2b77915dce22b0ce6fa477c2955d36d` | `b3e044315dca0b16b1790c9fe6de056b0a43ab2a4e2d93665809f014a351a8fb` |

v2에는 이전 11개 manifest 행을
`navigation_dataset_split_manifest_history_20260806`에 보존했다. 원본 v1 DB와
Review DB는 그대로 남아 있다. v2 `PRAGMA integrity_check`는 `ok`였다.

Review API는 v2 Runtime을 읽기 전용 source로 사용하며 다음을 확인했다.

- source database: `navigation-runtime-coverage-b-v2-ae3b7e0a.sqlite`
- source read-only: true
- reviewed: 133
- remaining raw decisions: 1,145

## 코드·계약 검증

GitHub Actions와 동일한 API 묶음을 정확한 release 디렉터리에서 실행했다.

- Python compileall: passed
- Decision Memory: passed
- public navigation prior: passed
- public task knowledge: passed
- public-prior A/B legacy diagnostic contract: passed
- 55셀 coverage contract: passed
- standards experience profile: passed
- interaction episode adapter: passed
- AndroidWorld research architecture: passed
- Runtime and safety gates: passed
- Android `testDebugUnitTest`: passed
- Android `assembleDebug`: passed

커버리지 validator 결과는 11개 앱, 55셀, 최종 12셀, 미완료 43셀, 위험 행동 자동 실행
0건이다.

## 배포 중 발견한 문제

첫 restart에서는 기존 `EnvironmentFile`이 새 `Environment=` 값을 덮어써 프로세스가
v1 Runtime을 계속 읽었고 `/status`가 split 불일치로 `ready=false`를 반환했다. 이때
실기기 수집 요청은 보내지 않았다.

우선순위가 가장 높은 `/srv/exitguide/runtime/navigation-runtime-coverage-v2.env`를
마지막 EnvironmentFile로 로드하도록 수정한 뒤 재시작했다. 실제 `/proc/<pid>/environ`에서
v2 Runtime, 새 manifest 경로와 `NAVIGATION_SERVER_RELEASE_ID=0dee4c8`을 확인했다.
재시작 후 `ready=true`, 연구 모델 준비, 공개 Prior 활성화와 11 collection을 확인했다.

## 팀 APK 배포

- release: `/srv/exitguide/releases/navigation-executor/0dee4c8`
- current symlink: `/srv/exitguide/releases/navigation-executor/current`
- APK SHA-256: `DED7802E765FE816D8035CA7DF7CDFC466E0489792D24B537CCBE5CD99FD299F`
- bundle: `navigation-executor-0dee4c8-team.zip`
- bundle SHA-256: `76D529E3C724DDBD6DB8E542B7D67FFB3EB368AB523C5BC9C23493CD0CE51293`
- bundle checksum verification: passed
- ZIP integrity: passed
- bundled PowerShell parser: passed

개인키와 API 비밀값은 bundle에 포함하지 않았다.
