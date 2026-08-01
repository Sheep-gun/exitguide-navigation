# Navigation DB self-feedback protocol

ExitGuide의 Navigation DB는 모델이 스스로 만든 답을 다시 정답으로
학습하는 구조가 아니다. 실패를 반복적으로 수집·분류하되, 정답의 출처와
튜닝 가능 여부를 분리해 카탈로그가 넓어질수록 오히려 검증 강도가 함께
높아지는 구조를 사용한다.

## 1. 데이터 계층

| 계층 | 용도 | 튜닝 사용 | 정확도 주장 |
|---|---|---:|---:|
| Reviewable catalog | 기능, 별칭, 문맥, 상태, 위험, 의미 경로의 단일 원본 | 사람 검토 후 가능 | 해당 없음 |
| Semantic development | 동의어·어간·결과 중심 목적 문장과 충돌 문맥 | 가능 | 불가 |
| Frozen independent | 별도 작성자가 고정한 목적·화면·행동 정답 | 정답 열람 후 튜닝 금지 | 합성 독립 성능 |
| Sealed realistic | 마지막에 한 번만 여는 현실형 holdout | 금지 | 제한된 blind 성능 |
| Catalog-derived | 카탈로그 문장 변형, route 변형, alias collision 전수 검사 | 가능 | 내부 일관성만 |
| Real-device gold | 사람이 단말에서 확인한 실제 화면·경로·시간 | 승인된 표본만 가능 | 실제 앱 성능 |

`tuning_allowed=false`인 실패는 제안 생성기와 K-EXAONE 분석 입력에서
자동으로 제외한다. 독립 세트의 기대값을 alias, pattern, rule로 복사하거나
모델 출력으로 기대값을 바꾸는 행위는 금지한다.

## 2. 한 번의 feedback cycle

`scripts/Run-NavigationDatabaseFeedback.ps1`은 다음 단계를 독립적으로
실행하고 결과를 `.artifacts/navigation-feedback/`에 남긴다.

1. 카탈로그를 두 번 재질화하고 두 파일의 SHA-256이 같은지 확인한다.
2. schema, 중복, 출처, 안전 경계, 최소 커버리지 품질 gate를 검사한다.
3. 다음 버전의 확장 초안이 있으면 영역·기능 수, 공식 출처, 보완 근거,
   기존 ID 충돌, 위험 경계를 canonical 승격 전에 별도로 감사한다.
4. 같은 UI 라벨을 공유하는 모든 function을 대상으로 문맥 분리 능력을
   검사한다.
5. 독립 fixture가 전체 intent와 function을 실제로 덮는지 감사한다.
6. 개발 목적 문장과 frozen 독립 목적 문장을 서로 다른 보고서로 평가한다.
7. 모든 intent의 한국어·영어 카탈로그 파생 장문을 생성해 중복·원문 복사·
   안전 경계·결정성·처리량을 검사하되 독립 정확도로 집계하지 않는다.
8. loading, error, re-login, permission, WebView, dialog, endless feed,
   icon-only, disabled control, scroll, backtrack을 포함한 상태형 경로를
   실행한다.
9. catalog-derived 변형 전체에서 goal resolver의 불변성과 충돌을 검사한다.
10. 실패 원인과 변경 후보를 quarantine 보고서로 만들며 자동 적용하지 않는다.

각 단계는 앞 단계의 성공 상태를 재사용하지 않는다. 네이티브 프로세스의
종료 코드도 단계마다 초기화하므로 오래된 성공 코드가 현재 실패를 가리지
못한다.

## 3. 최적화 목표와 우선순위

최적화는 다음 lexicographic 순서를 사용한다. 아래 항목을 희생해 위의
숫자만 높이는 변경은 채택하지 않는다.

1. 위험 클릭 수 `0`
2. 잘못된 클릭 수 `0`
3. frozen independent goal 해석 유지
4. 목적지 도달률과 안전 정지율
5. alias collision 분리율
6. 탐색 시간과 클릭·스크롤·뒤로 가기 수
7. catalog-derived 변형 통과율

해지, 결제, 송금, 제출, 삭제, 권한 변경, 동의 체크처럼 외부 상태를
바꾸는 제어는 `never_auto`이며 `before_action`에서 멈춘다. 탐색 성공률을
올리기 위해 이 경계를 완화하지 않는다. 시험의 기대 클릭과 충돌하더라도
안전 정지를 보존하고 그 케이스를 명시적인 보수 실패로 기록한다.

## 4. 실패 분류

실패는 최소한 다음 원인 중 하나로 분류한다.

- `goal_generic`: 목적이 특정 intent로 좁혀지지 않음
- `goal_collision`: 다른 intent의 동의어·결과 표현과 충돌
- `alias_collision`: 동일 버튼 이름을 문맥으로 구별하지 못함
- `gateway_missing`: 계정, 전체 메뉴, 설정, 로그인 같은 관문 누락
- `destination_missed`: 목적 기능이 보이는데 목적지로 판정하지 못함
- `premature_destination`: 중간 화면을 최종 목적지로 오인
- `safe_menu_not_explored`: 안전한 다음 메뉴를 탐색하지 않음
- `wrong_menu`: 목적과 다른 메뉴를 선택
- `scroll_loop`: 반복 화면이나 무한 피드에서 계속 스크롤
- `recovery_failure`: loading/error/offline/re-login/permission 상태에서 복구 실패
- `unsafe_action`: 사용자 소유 동작을 자동 실행하려 함
- `performance_regression`: 성공하지만 시간·상호작용 횟수가 악화

한 실패를 고칠 때는 앱명, package name, 화면 좌표, fixture case ID를
런타임 규칙에 넣지 않는다. 기능 의미, role, 상태, 주변 문맥, 그래프 구조,
화면 fingerprint처럼 다른 앱에도 재사용되는 근거만 허용한다.

## 5. 변경 승격 조건

변경 후보는 다음 조건을 모두 만족해야 canonical catalog로 승격할 수 있다.

- 근거가 공식 1차 문서 또는 사람이 검증한 실제 화면이다.
- function/intent ID와 정규화 pattern 충돌이 없다.
- 한국어·영어 별칭, 긍정·부정 문맥, 상태·위험 cue가 있다.
- state-changing/high-risk 기능은 `never_auto`와 실행 전 정지를 사용한다.
- materializer가 byte-for-byte idempotent다.
- 기존 독립 세트와 안전 회귀가 악화되지 않는다.
- 개선에 사용한 development set과 사용하지 않은 independent set의 결과를
  별도로 남긴다.
- K-EXAONE 제안은 `auto_apply=false`, `review_required=true` 상태로만 남는다.

## 6. 실행

```powershell
# 빠른 반복: 대표 충돌, 모든 독립 상태형 세트, fast robustness
.\scripts\Run-NavigationDatabaseFeedback.ps1 -Mode quick

# 전체 exact-alias 충돌과 full catalog-derived 변형
.\scripts\Run-NavigationDatabaseFeedback.ps1 -Mode full

# 더 큰 합성 조합, 장시간 회귀, V16 임시 materialization 후보 계약
.\scripts\Run-NavigationDatabaseFeedback.ps1 -Mode deep

# deep 외 모드에서 V16 승격용 실제 격리 평가를 명시적으로 요청할 때만
.\scripts\Run-NavigationDatabaseFeedback.ps1 -Mode full -RunIsolatedPromotionEvaluation
```

보고서의 `status=pass`는 해당 cycle이 선언한 gate를 통과했다는 뜻이다.
실제 Android 앱에서 정확하다는 뜻은 아니며, 그 주장은 `real_device_gold`
표본이 생긴 뒤 앱 버전·기기·locale과 함께 별도로 계산한다.

## 7. V16 격리 후보 단계

표준 피드백 cycle은 V16 fixture adapter 다음에 계약 검사를 실행하고,
`Mode=deep` 또는 `-RunIsolatedPromotionEvaluation`을 명시한 경우에만 실제 격리 평가를 실행한다.

1. `v16_isolated_evaluation_contract`가 격리 병합, fixture seal, 집계 전용 출력과 안전 gate의
   코드 계약을 검사한다.
2. 선택적인 `v16_isolated_candidate_evaluation`이 canonical V15를 읽기 전용으로 유지한 채
   V16 후보를 메모리·임시 디렉터리에서 평가하고 집계 보고서만 저장한다. 약 한 시간 규모의 봉인된
   승격용 실행이므로 `quick`/`full`의 일반 개발 되먹임에는 자동 포함하지 않는다.

두 단계는 V16을 canonical에 materialize하거나 자동 승격하지 않는다. 봉인된 실패 문장과 case
식별자는 저장하거나 튜닝 입력으로 되돌리지 않으며, K-EXAONE 제안에도 자동 적용 권한을 주지
않는다. `--gate`는 위험 클릭 0, 960개 projection 사례의 위험 클릭 선언 0, 기권 사례 100%
안전 정지/no-click, 자동 최종 누름 0, 사용자 소유 최종 누름을 요구한다. 실제 격리 평가 결과를
검토해 기준선을 합의하기 전까지 정확도 하한은 0 기본값으로 두므로, 이 단계의 pass만으로 성능
승격을 선언해서는 안 된다.

`Mode=deep`은 추가로 `v16_materialization_candidate_contract`를 실행한다. 이 검사는 canonical
V15의 임시 복사본에 V16 후보를 적용해 191개 영역·3,118개 기능·2,900개 intent, equivalence
물리/논리 기능 3,118/3,108개, intent 2,900/2,890개, 기본 terminal 2,898/2,888개와 동치
클래스/alias 10/10개를 확인한다. 두 번 적용한 byte idempotence, 부분 V16 삽입과 equivalence
변조의 fail-closed, canonical 원본 불변도 함께 검사한다. 측정된 실행은 578.8초 PASS였다.
9~10분 비용 때문에 `quick`과 `full`에서는 이 단계를 실행하지 않으며, 이 검증도 canonical V16
승격을 자동 승인하지 않는다.

첫 `v16_isolated_candidate_evaluation` actual은 stateful 입력의 500자 schema 경계에서 멈춰
aggregate를 만들지 못했다. 수정 후에도 goal-only 평가는 봉인된 원문을 그대로 사용하며,
stateful consumer용 복사본만 결정적으로 최대 500자로 projection한다. 이 계약 unit은 117.6초에
PASS했고 actual 재평가는 진행 중이다. 완료 보고서가 나오기 전에는 정확도 수치나 새 gate 하한을
추정하지 않는다.
