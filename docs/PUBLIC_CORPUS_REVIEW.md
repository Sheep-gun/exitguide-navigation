# 공개 약관 검토 절차

이 문서는 AI Hub 019 약관과 공정거래위원회 표준약관의 조항화 결과를 사람이 검토하는 절차를 정의한다. 표본 패킷 생성은 규칙 기반이며 검색 승인, 법률 판단, 라이선스 판단을 자동 수행하지 않는다.

## 패킷 생성

조항화 결과를 먼저 만든다.

```powershell
.\scripts\Process-PublicCorpus.ps1
.\scripts\New-PublicCorpusReviewPacket.ps1
```

기본 출력은 `.artifacts/review-packets/public-corpus-v1`이다.

| 파일 | 용도 |
| --- | --- |
| `review-checklist.csv` | Excel에서 작성할 사람 검토표 |
| `review-items.jsonl` | 원문 provenance와 구조를 보존한 기계 판독본 |
| `summary.json` | 입력·출력 hash, 모집단과 표본 건수 |
| `README.md` | 패킷 안에서 바로 읽는 짧은 작성 안내 |
| `source-review.json` | 출처별 이용 조건과 local-search 허용 검토 |

기본 설정은 source와 stratum별 최대 8건을 SHA-256 순위로 선택한다. 임의 난수를 쓰지 않으므로 입력이 같으면 표본과 출력 hash도 같다. 2026-07-15 현재 패킷은 AI Hub 114건, 공정위 29건으로 총 143건이다.

## 표본 층

- 정상 조항
- 정확 포함으로 연결된 AI Hub annotation
- 5-gram 점수 0.90 이상, 0.80 이상, 0.72 이상 경계 연결
- 낮은 점수, 짧은 표본, 복수 후보 때문에 연결하지 않은 annotation
- 중복 조 번호, 역순 조 번호, 조 번호 없음
- 짧거나 긴 section, 큰 preamble, 의심 Unicode

각 item은 최대 3,000자 발췌만 포함한다. 긴 section은 앞과 뒤를 보이고 중간 생략을 표시한다. 패킷은 review 편의를 위한 파생 artifact이며 공개 fixture가 아니다.

## 작성 값

`review-checklist.csv`의 빈 열만 작성한다.

| 열 | 허용 값 |
| --- | --- |
| `license_status` | `unknown`, `research_only`, `redistributable`, `blocked` |
| `privacy_status` | `clear`, `redaction_required`, `blocked` |
| `parse_quality` | `pass`, `minor_issue`, `major_issue` |
| `annotation_quality` | `correct`, `incorrect`, `uncertain`, `not_applicable` |
| `final_decision` | `candidate_for_search`, `needs_followup`, `reject` |

`reviewer`와 `reason`도 반드시 작성한다. `license_notes`는 검토 단서일 뿐 재배포 허가를 증명하지 않는다. 약관 본문에 일반 연락처가 존재할 수 있으므로 개인정보 판단에서는 실제 사용자·계정·거래·인증정보와 공개 사업자 연락처를 구분한다.

`source-review.json`에는 출처별 `license_status`, `local_search_allowed`, reviewer, reason, timezone이 포함된 `reviewed_at`, 근거 URL을 작성한다. `local_search_allowed: true`는 `research_only` 또는 `redistributable`에서만 허용되며 근거 URL이 반드시 필요하다. 패킷 재생성은 기존 `source-review.json`을 덮어쓰지 않는다.

## 검증과 pending import

검토 중에도 명령을 실행할 수 있다. 완전히 빈 행은 오류가 아니라 pending으로 집계되며, 일부 열만 작성한 행과 허용값 밖의 값은 거부된다.

```powershell
.\scripts\Validate-PublicCorpusReview.ps1
.\scripts\Import-ReviewedPublicCorpus.ps1
```

두 번째 명령은 기본적으로 dry-run이다. `candidate_for_search` 행이 source-level 허용, `privacy_status: clear`, `parse_quality: pass`를 모두 충족하는지 확인하고 예상 문서·section 수만 보여 준다.

dry-run 결과를 확인한 뒤에만 pending registry에 적용한다.

```powershell
.\scripts\Import-ReviewedPublicCorpus.ps1 -Apply
```

`-Apply`도 검색 승인이 아니다. 통과 section을 원문 hash와 다시 대조하고 문서별 current version으로 묶어 `pending_review` 상태로 저장한다. review item과 source review hash는 별도 audit table에 기록된다. 최종 검색 승인은 대상 version마다 `Review-TermsDocument.ps1`을 사용한다.

## 승인 경계

`candidate_for_search`는 패킷 수준의 후보 표시다. 다음을 자동으로 수행하지 않는다.

- SQLite `approved_for_search` 상태 기록
- Git fixture 공개 승격
- 전체 source 일괄 승인
- 법적으로 유리하거나 불리한 조항 확정

또한 validator/importer는 다음을 거부한다.

- 패킷에 없는 item ID 또는 누락·중복 ID
- source, stratum, document ID 변조
- timezone이나 근거 URL이 없는 source 승인
- source 이용 조건과 행의 license 상태 불일치
- 개인정보 또는 parse 상태가 통과하지 않은 검색 후보
- processed section과 검토표의 content hash 불일치
- 같은 section에 대한 서로 다른 최종 결정

작성된 표본이 충분히 일관적인지 확인한 뒤, public-section importer로 source, document version, section hash, license/privacy 상태를 pending registry에 기록한다. 독립 retrieval gold set이 준비되기 전에는 공개 조항을 최종 검색 승인하지 않는다.

현재 실제 패킷 검증 결과는 pending 143건, 완료 0건, importable 0건이다.
