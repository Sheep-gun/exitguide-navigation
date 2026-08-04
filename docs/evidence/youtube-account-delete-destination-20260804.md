# YouTube account.delete 실기기 목적지 검증 — 2026-08-04

## 결론

- 앱/버전: YouTube `com.google.android.youtube`, `21.31.524+1561190182`
- 기기: Samsung SM-S936N, Android 16, locale `ko-KR`
- B 고정 공개 Prior: `enabled=true`
- 최종 유효 세션: `navs_46bdd8ecf95547ddbc30af27da18c74a`
- 결과: `destination_reached`, Destination Signature match `0.82`
- 마지막 안전 행동: `scroll(down)`
- 최종 관찰 후보: `a11y_55543879af66e5744fb2`, `Google 계정 삭제`
- 최종 후보 안전 분류: `risk_level=high`
- 계정 삭제 후보 클릭: 0회
- 위험 행동 자동 실행: 0건

## 실제 경로와 검증 결과

| 단계 | 행동 | 관찰 결과 |
|---:|---|---|
| 0 | `click(내 페이지 candidate_id)` | YouTube 계정 화면으로 이동 |
| 1 | `click(계정 candidate_id)` | 계정 선택·관리 영역으로 이동 |
| 2 | `click(Google 계정 관리 candidate_id)` | `com.google.android.gms` 계정 관리 UI로 정상 handoff |
| 3 | `click(데이터 및 개인 정보 보호 candidate_id)` | 개인정보 허브로 이동 |
| 4 | `wait_and_observe()` | VLM용 재관찰, 클릭 없음 |
| 5 | `scroll(down)` | 개인정보 허브 하단 탐색 |
| 6 | `wait_and_observe()` | VLM용 재관찰, 클릭 없음 |
| 7 | `scroll(down)` | `Google 계정 삭제` 후보가 보이는 목적지 도달 |

모든 클릭은 해당 화면에서 Accessibility가 발견한 candidate_id로 실행됐다. 임의 좌표,
Gold 경로 재생, AndroidControl DB, 앱 패키지별 고정 경로는 사용하지 않았다.

## 실기기에서 발견하고 수정한 오류

1. 명시적 provider 계정 관리 화면 전환이 `external_app/regressed`로 잘못 기록됐다.
   선택한 provider gateway와 도착 화면의 계정 의미가 모두 확인되면 일반적인 K² 중간
   목적지 진행으로 인정하도록 수정했다.
2. `데이터 및 개인 정보 보호` 도착 화면의 한국어 문구가 토큰으로 분리되어
   `semantic_distance_increased`로 오판됐다. compact/split 개인정보 토큰을 모두
   인식하도록 수정했다.
3. `개인정보 보호 진단`을 계정 삭제 경로로 잘못 선택하고 `YouTube 기록 자동 삭제`를
   계정 삭제 목적지로 오인한 세션 `navs_6d3d968a5311433fb60f15ae9a0c4a16`은 거짓
   성공으로 판정해 승격에서 제외했다. 계정 삭제 Destination Signature는 동일한 직접
   영역에 계정 정체성과 삭제 의미가 함께 있어야 하며 기록·활동·프로필 삭제는 제외한다.
4. 개인정보 허브에 명시적 계정 삭제 후보가 아직 없으면 진단·추천 카드를 누르지 않고
   제한된 `scroll(down)`을 우선하도록 수정했다.
5. Android Executor가 `Google 계정 삭제`를 low risk로 보고하던 문제를 수정하고 APK를
   재설치해 같은 실기기 화면에서 `risk_level=high`를 확인했다.

관련 구현 커밋은 `22c038c`, `3e5c5cd`, `a4881f4`다. 최신 `a4881f4`는 로컬과 N100에서
API 단위 테스트 10/10을 통과했고, Android `testDebugUnitTest`와 `assembleDebug`도
통과했다.

## 실행 지표

- 총 의사결정: 8
- candidate_id 클릭: 4
- 스크롤: 2
- 재관찰: 2
- 잘못된 클릭: 0 (최종 유효 세션 기준)
- 실행 성공: 8/8
- 세션 시간: 약 175초
- semantic fast path: 2/8
- Solar 판단: 4/8
- VLM 화면 해석: 5/8
- 연결 오류: 0
- 위험 행동 자동 실행: 0

공개 Prior는 매 단계 advisory evidence를 반환했지만 같은 GUI-Odyssey 항목이 반복됐고,
이 세션에서 경로 결정에 유효한 고유 근거였다는 증거는 없다. 따라서 공개 Prior의 유효
근거율 개선이 입증됐다고 주장하지 않으며, B를 끄지 않고 이후 Retriever 관련성 개선
대상으로 보존한다.

## 표준 승격 상태

collection 앱 경험이므로 최종 유효 세션만 다음 표준 계층으로 변환했다.

`Runtime DB → interaction-episode.v1 → knowledge-promotion.v1 draft`

- N100 episode: `/srv/exitguide/runtime/promotion-youtube-account-delete-final-20260804/interaction-episodes.jsonl`
- episode SHA-256: `22cc11f139105eb8636fad1851ad610f6c25d12627c84b614c1765b0ac10029e`
- episodes/steps: 1/8
- N100 promotion candidates: `/srv/exitguide/runtime/promotion-youtube-account-delete-final-20260804/promotion-candidates.jsonl`
- candidate SHA-256: `638341693a12dd50b213eee8441ec36ecb066ca98ead4f434cdcd01324b0ca0b`
- draft candidates: 5, support count 1
- accepted: 0
- App Knowledge generation: 0
- Decision DB projection: 0

반복 검증·승인 전이므로 draft를 자동 승인하거나 Decision DB에 직접 삽입하지 않았다.
