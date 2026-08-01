# ExitGuide Navigation DB 확장 중단 및 최종 상태 보고서

- 기준 시각: 2026-07-30 (Asia/Seoul)
- 브랜치: `agent/universal-navigation-agent`
- 상태: 장기 DB 확장 중단
- 동결 규칙: V21은 연구 문서까지만 보존하며 구현하지 않는다. V22 이후 신규 DB 버전은 사용자 지시 없이 만들지 않는다.
- 게시 상태: 최초 동결 시점에는 미커밋이었으며, 이후 사용자 지시에 따라 이 보고서가 정한 DB 범위만 현재 브랜치에 커밋·푸시한다. 이는 candidate의 canonical 승격을 의미하지 않는다.

## 1. 결론

물리적 canonical은 계속 V15이다. V16~V20은 메모리 병합형 후보 계층이고 canonical 파일에 반영되지 않았다. V21은 연구 문서만 존재한다.

| 구분 | 상태 | 영역 | 기능 | 목적(intent) | 핵심 판정 |
|---|---:|---:|---:|---:|---|
| V15 canonical | 물리적 기준 | 179 | 2,866 | 2,660 | 현재 유일한 canonical |
| V16 candidate | 후보 | 191 | 3,118 | 2,900 | 공개 개발 회귀 PASS, 기존 blind promotion 평가는 FAIL |
| V17 candidate | 후보 | 203 | 3,358 | 3,128 | 데이터/독립 픽스처 존재, 최종 독립 runtime 평가는 미실행 |
| V18 candidate | 후보 | 215 | 3,610 | 3,368 | data unit PASS, 독립 semantic runtime 평가는 미실행 |
| V19 candidate | 후보 | 224 | 3,733 | 3,482 | full data unit PASS, 독립 semantic runtime 평가는 미실행 |
| V20 candidate | 후보 | 232 | 3,869 | 3,610 | data unit PASS, runtime 최종 PASS는 미확인 |
| V21 research | 연구 전용 | 238 전망 | 3,975 전망 | 3,710 전망 | 문서만 존재, 구현/테스트 없음 |

## 2. Canonical 기준

### V15 function catalog

- 파일: `fixtures/navigation/function-catalog.v1.json`
- `catalog_version`: `15.0.0`
- 크기: 220,158,014 bytes
- SHA-256: `e0eeef03195a48ec8172421926d08c30823bc678c72ea72082bb513dbec36e24`
- 영역 179개, 기능 2,866개, intent 2,660개

### Function equivalence

- 파일: `fixtures/navigation/function-equivalence.v1.json`
- 크기: 19,165 bytes
- equivalence class 10개
- SHA-256: `197aa0253c0353e439a6679a3597efed25297c44c554a15c0402a30f077ab2e8`

V16~V20의 `merge_with_base` 결과는 physical canonical에 쓰지 않았다. 따라서 후보 테스트가 PASS여도 canonical 승격을 의미하지 않는다.

## 3. 후보 계층별 상태

### V16

- 신규분: 영역 12개, 물리 기능 252개, intent 240개
- 누적 전망: 영역 191개, 기능 3,118개, intent 2,900개
- 데이터 파일: `scripts/navigation_catalog_v16_data.py`
- 파일 SHA-256: `8b6d5cc55f217bacf71b98de67be77b9255ab334e26f849be679718297e56866`

기존 blind isolated evaluation은 완료됐지만 품질 gate를 통과하지 못했다.

- 평가 보고서: `.artifacts/navigation-v16-isolated-evaluation/aggregate-report.json`
- 보고서 SHA-256: `9cac9cb1a19dcb774b9e4d92c3871bcb9dda2a750dd6a94a27bd0d1c162b5bbd`
- 목적 해석 성공: 33/840 = 3.9286%
- stateful routable: 306/840 = 36.4286%
- abstention no-click: 93/120 = 77.5%
- combined: 399/960 = 41.5625%
- wrong click: 55.8333%
- unsafe click: 0%
- 자동 위험 최종 동작: 0/960
- 판정: `gate.passed=false`, 승격 불가

blind 결과를 읽지 않고 공식 공개 개발 표본만 사용한 resolver 보정은 마지막 실행에서 PASS했다.

- 장문 96건: target 44, generic fail-closed 52, wrong 0
- ambiguity 12건: generic 12, guessed 0
- 유지 회귀: semantic positive 480 / negative 960, collision 720, recovery 960, isolation 720, exact/wrapper 2
- markerless class1 보존 12, explicit-marker class1 확인 96
- governance probe 804, provider call 0, dangerous final 0
- 실행 시간: 226.2초
- `py_compile`, whitespace/diff 검사 PASS

현재 보정 파일:

- `apps/api/app/services/navigation_function_catalog.py` — SHA-256 `419919dc938401e21f0cba0765e205ac2948457f62dbe20b17fe6aff17668783`
- `apps/api/app/services/universal_navigation_agent.py` — SHA-256 `05dedfd5931869fe159986aad97870bec3f3c34b715aaa78dd710c85578b27ee`
- `apps/api/tests/navigation_catalog_v16_runtime_probes_unit.py` — SHA-256 `1513c40b951c28377de329054d27c59677673f03fb67327e8768717e496e76f0`

이 공개 개발 PASS는 기존 blind promotion FAIL을 덮어쓰지 않는다. 새로운 독립 sealed 재평가는 중단 지시에 따라 실행하지 않았다.

### V17

- 신규분: 영역 12개, 기능 240개, intent 228개
- 누적 전망: 영역 203개, 기능 3,358개, intent 3,128개
- layer SHA-256: `906194051e9b211f6d6a7719c2b5bdae4961e6e439d0660ed79a75565fabfb4d`
- 데이터 파일 SHA-256: `03adc06839a52fe6751ebf7fc23d5616a800a1fbd13860ae89df4ae63cc02988`
- S 95 / C 133

독립 fixture는 구현/runtime을 보지 않고 작성됐다.

- 파일: `fixtures/navigation/db-gym/independent-public-case-v17.v1.json`
- 12개 영역, 228 cases, 912 steps
- SHA-256: `014efca401177aedb3e0ef147883ddbc5826f7d181582ee23628e42240c91563`
- 구조 unit 8/8 PASS
- 실제 runtime 결합 평가는 미실행

### V18

- 신규분: 영역 12개, 기능 252개, intent 240개
- 누적 전망: 영역 215개, 기능 3,610개, intent 3,368개
- layer SHA-256: `5037b41f24de175d9100a1bcc2c82efa438dfd00abeffaf9018282d797f37d99`
- 데이터 파일 SHA-256: `ae1fffaa1ba6101c748ef7cccaf530fa2fb70ef9ceca7d1b84b482c3ade87be5`
- 연구 문서 SHA-256: `cca4aac49ad2811dfb1d55e059628c7261723becec6fd27536a648fddf9f5c13`
- 공식 출처 110개, S 126 / C 114

검증:

- data unit PASS, 196.9초
- collision 120, semantic 1,440, recovery 960, role/asset 720 구조 검증 PASS
- 독립 fixture: 240 cases / 960 steps, 한글 120 / 영문 120
- fixture SHA-256: `10bdad769164b0c3429a9d74deb58fcd0e3eaa8d156628202fe0e28251fc63df`
- V18/V19 fixture 구조 unit 9/9 PASS
- 독립 fixture는 `runtime_bound=false`; semantic adapter 및 실제 runtime 평가는 미실행

### V19

- 신규분: 영역 9개, 기능 123개, intent 114개
- 누적 전망: 영역 224개, 기능 3,733개, intent 3,482개
- layer SHA-256: `4438e2745075abc00a4d4adeb3aac661c1417affb24835c6955e09f353197587`
- 데이터 파일 SHA-256: `a18d08432d226b0d10fc8468c028cbfcde4a643caa3fb132634c0e1a086978a0`
- 연구 문서 SHA-256: `f5997e4728a3131b995d2796a9b61cc943aeaf66d82d1e1ee3b5da811dc27d6b`
- official-source registry SHA-256: `974591e7c12300b51a301572a8d2058b6809f40836df18ba87864bf6a60315ca`
- 공식 출처 73개, S 52 / C 62
- localization correction 13개, 비한글 allowlist 3개

검증:

- full data unit PASS, 301.6초
- semantic 684, collision 122, recovery 456, role/asset 342
- 입력 불변성, 멱등 병합, localization 복원, source reverse mapping, tamper/fail-closed PASS
- 독립 fixture: 114 cases / 456 steps, 한글 57 / 영문 57
- fixture SHA-256: `b8f6da0bb04a60c30b554af50421bb80fec3976b1d53b913dbe9d92282f94fd2`
- 독립 fixture semantic adapter 및 실제 runtime 평가는 미실행

### V20

- 신규분: 영역 8개, 기능 136개(터미널 128 + hub 8), intent 128개
- 누적 전망: 영역 232개, 기능 3,869개, intent 3,610개
- layer SHA-256: `5344e860bf7939952f4eb37a94eeb1275687fa7b930ab1cb97711808360321e8`
- V19 composed payload SHA-256: `e7d7d53145e1769a0320716014b9bfdc7ce8e700bed82f3aab606732ededd5b1`
- 연구 문서 SHA-256: `b9fb9cfc3b0d6b8ca1120f5cc01624ee8f926687f4f86cc50301ca50f595296e`
- official-source registry SHA-256: `3fd21a7de7f926067352dfe4ecb357cb330683668b16608ac40e36e951cb020f`
- 공식 출처 63개, S 76 / C 52
- 모든 터미널: `never_auto`, `before_action`, `user_owned_final_press=true`

V20 검증에서 V17/V18 상속 데이터의 미존재 `avoid_functions` 1,314건을 발견했다.

- 고유 bad ID 54개, owner intent 354개
- 확정 치환 46개, 모호하여 fail-closed 제거 8개
- 적용 전 unknown 1,314, 적용 후 0, 역변환 후 원본 정확 복원
- correction contract SHA-256: `efcd39ed6f4c8bf4568491d7c6dafe7096f2d24f5f25908c8342453eecce8de6`
- preimage SHA-256: `e43758f32c87e910bcaefa0cc34b50a6b573c6a96cd1dc63cab781fc328188dd`

최종 파일:

- `scripts/navigation_catalog_v20_data.py` — SHA-256 `d5745198cf21e7b56fba510212b506eea37a4962e769b11ae14ba8fbd2671a2d`
- `apps/api/tests/navigation_catalog_v20_data_unit.py` — SHA-256 `4ce9cb132a0c350013fc81c38b660ea41eb44879681284f07fb831eb283c7c41`
- `apps/api/tests/navigation_catalog_v20_runtime_probes_unit.py` — SHA-256 `c105d82ba3a019f779c3a5c848e96dd9e4281bec0a57bd48227307b582cd4028`

검증 상태:

- 최종 파일 `py_compile` 및 diff/static cue audit PASS
- correction 포함 data unit PASS, 371.0초
- 이후 runtime probe 문구를 실제 `negative_context` 기반으로 수정했으므로 현재 세 파일의 정확한 조합으로 data unit을 재실행하지는 않음
- runtime 1차 FAIL: V17/V18 unknown reference 1,314건
- runtime 2차: correction 적용 및 catalog import/unknown=0 통과, 실제 probe 단계 진입 후 `missing_role` 개발 문구와 runtime cue 불일치로 FAIL
- probe 문구 수정 및 정적 검사는 PASS
- 사용자 중단 지시에 따라 runtime 3차는 실행하지 않음
- 최종 판정: 데이터 후보는 보존, runtime PASS는 주장하지 않음

### V21

- 상태: 연구 문서만 존재
- 채택 연구 영역 6개, terminal 100개 + hub 6개
- 전망: 영역 238개, 기능 3,975개, intent 3,710개
- 공식 URL 66개, 27개 공식 host, 기존 충돌 ID 64개 확인
- 연구 문서 SHA-256: `6999fa1f80f25fadea0729eecca7f46c8dd21dd605dc97b3565ed9e465479595`
- 채택 연구 영역: USCIS 사후접수, Medicare 수급자, Lifeline 통신 지원, ADA paratransit, 범죄피해자 보상, 재산세 감면
- 여권·보훈·Social Security·학생지원·재난지원·공공주택·실업급여 등 기존 V17 중복군은 거절
- `scripts/navigation_catalog_v21_data.py` 없음
- V21 data/runtime test 없음
- V22 이후 관련 소스 산출물 없음

## 4. 테스트 원장

| 테스트/평가 | 최종 상태 | 비고 |
|---|---|---|
| V16 isolated blind evaluation | FAIL | 안전 최종동작 0이지만 정확도 gate 실패; 승격 불가 |
| V16 public-development regression | PASS | wrong 0, guessed 0, 기존 회귀 보존; blind 재평가 아님 |
| V17 데이터 정적 감사 | PASS | 계층 SHA/수량/안전 경계 확인 |
| V17 독립 fixture 구조 unit | PASS 8/8 | runtime 미결합 |
| V18 data unit | PASS | 196.9초 |
| V19 full data unit | PASS | 301.6초 |
| V18/V19 독립 fixture 구조 unit | PASS 9/9 | runtime 미결합 |
| Navigation performance unit | PASS | 기존 탐색시간/상호작용 우선순위 검사 |
| V20 data unit | PASS | 371.0초; 이후 runtime probe 테스트 파일 문구 변경 |
| V20 runtime probe 1차 | FAIL | 상속 unknown reference 1,314건 발견 |
| V20 runtime probe 2차 | FAIL | catalog import는 통과, 개발 probe cue 불일치 |
| V20 runtime probe 3차 | 미실행 | 중단 지시 준수 |
| V21 data/runtime | 미구현 | 연구 문서만 보존 |

## 5. 독립 평가 자산

- V17: 228 cases / 912 steps
- V18: 240 cases / 960 steps
- V19: 114 cases / 456 steps
- 총 582 cases / 2,328 steps
- 모든 독립 사례는 `no_click`, `stop_before_action`, 사용자 최종 클릭 소유를 요구한다.
- V18/V19는 구현 ID를 추측하지 않고 `expected_semantic_key`로 봉인했으므로, 재개 시 일회성 semantic adapter를 별도 작성·봉인해야 한다.

## 6. 미완료 항목

1. V16 공개 개발 보정에 대한 새로운 독립 sealed promotion 평가는 실행하지 않았다.
2. V17 독립 fixture의 실제 runtime 결합 평가는 실행하지 않았다.
3. V18/V19 독립 fixture semantic adapter 및 실제 runtime 평가는 실행하지 않았다.
4. V20 현재 최종 파일 조합의 data unit 재실행과 수정된 runtime probe 재실행은 하지 않았다.
5. V20 probe 본문은 layer digest에 포함되지 않는다. 재개 시 probe 산출물 자체를 별도 봉인해야 한다.
6. V21은 연구만 존재하며 구현하지 않았다.
7. V16~V20 어느 후보도 physical canonical에 materialize/promote하지 않았다.
8. 휴대전화 연결·APK 실기기 검증은 이 확장 단계에서 수행하지 않았다.
9. 중단된 V16 isolated 실행이 만든 외부 TEMP 디렉터리 3개가 남아 있다. 내용은 열람하지 않았고 정책상 삭제하지 않았다. 성공한 aggregate report는 repo의 `.artifacts`에 별도 보존돼 있다.

## 7. 최초 동결 시점의 Worktree 상태

- 브랜치: `agent/universal-navigation-agent`
- 상태 항목 206개: modified 29개, untracked 177개
- dirty worktree에는 기존 사용자 작업과 이번 후보 산출물이 함께 있으므로 일괄 reset/clean 하면 안 된다.
- 최초 중단 시점에는 커밋·푸시·canonical 교체를 수행하지 않았다. 이후의 DB 범위 커밋·푸시는 보존·공유를 위한 것이며 canonical 파일의 버전은 계속 V15다.

## 8. 재개 조건

이 보고서 이후에는 사용자 지시 없이 V21 구현, V22 연구/구현, 추가 공식자료 수집, 후보 promotion을 자동 수행하지 않는다.

재개 요청이 있을 경우에도 새 버전 생성보다 먼저 다음 순서를 권장한다.

1. V20 현재 파일 조합의 data unit 재실행
2. V20 수정 runtime probe 재실행
3. V17~V19 독립 fixture adapter 작성 및 blind runtime 평가
4. V16 새 sealed promotion 평가
5. 모든 gate가 통과한 후보만 별도 승인 후 canonical 승격
