# Consent Case Data Collection Policy

ExitGuide needs Korean consent, terms, cancellation, and dark-pattern examples, but the repository must stay safe to share and easy to audit. This policy applies before adding any real or field-derived case to `fixtures/consent-cases/cases.json` or promoting any captured terms document into `fixtures/terms-corpus/documents.json`.

## Allowed Fixture Types

- `synthetic`: Authored test cases that do not come from a real user session or real account data.
- `field_candidate`: A generalized pattern observed in the field, rewritten as text-only fixture data with no raw screenshot, account detail, provider-specific personal data, or unique transaction detail.
- `captured_redacted`: A real user-submitted or manually captured case that has been redacted, reviewed, and approved for fixture use.

Raw screenshots, raw OCR dumps, account names, phone numbers, emails, addresses, order IDs, payment details, membership IDs, device identifiers, auth tokens, cookies, headers, and support-chat transcripts are not allowed in the repository.

## Intake Workflow

1. Capture or receive the material outside the repository.
2. Strip or generalize all personal, account, transaction, device, and provider-specific details.
3. Convert the case into the fixture shape: `screen_title`, `screen_text`, `elements[]`, expected risk, expected direction, tags, and data notes.
4. Fill the `source` object.
5. Run the backend test suite before committing or archiving the work.

The fixture should describe the consent pattern, not preserve the user's original artifact.

## Terms Corpus Capture Workflow

Automated collectors such as OpenClaw and manual copy/paste collection must write raw terms captures outside the source tree, preferably under `.artifacts\terms-captures\inbox`. The accepted JSON shape is one object, an array, or `{ "captures": [...] }`; each capture should include `source_url`, `service_name`, and either `raw_text` or `html`.

Use:

```powershell
.\scripts\Import-TermsCaptures.ps1 -InputPath .\.artifacts\terms-captures\inbox
```

The importer normalizes captures into `.artifacts\terms-corpus.sqlite`, records content hashes and import status in `terms_capture_staging`, records current accepted versions in `terms_sources` and `terms_document_versions`, rejects obvious private data candidates, and keeps imported real-site text out of repository fixtures by default.

An imported document is registered as `pending_review` and is not added to `terms_documents`, `terms_chunks`, FTS5, or API search results. Only a current version with the exact status `approved_for_search` is rebuilt into the retrieval tables.

The importer is deliberately strict for collection hygiene:

- Captures must explicitly resolve to `retrieval_status: "captured"`.
- Failed, partial, blocked, login-required, captcha, timeout, missing, or unknown status captures are rejected.
- `locale` must be `ko-KR`.
- URL query strings and fragments are stripped before storage.
- Imported captures cannot self-mark `public_fixture_allowed`; that flag is ignored during import.
- Reimported exact-text captures are treated as duplicates across runs.

Only promote a captured terms document into `fixtures\terms-corpus\documents.json` after:

- The source is public and the usage/license risk is reviewed.
- The text contains no account, transaction, cookie, token, support-chat, or user-specific data.
- `public_fixture_allowed` is intentionally set.
- The backend unit checks and archive-safety checks pass.

## Public Dataset Normalization Workflow

수집한 공개 원본과 수동 다운로드한 AI Hub, Open Terms Archive, Princeton 원본은 다음 명령으로 공통 staging JSONL로 변환한다.

```powershell
.\scripts\Convert-PublicTermsDatasets.ps1
```

adapter는 원본을 수정하지 않으며 ZIP entry와 CSV를 스트리밍으로 읽는다. Princeton XZ만 생성 artifact인 SQLite로 풀어 관계형 구조를 확인한 뒤 고유 정책 본문과 전체 시점 provenance를 결합한다. 출력은 `.artifacts\normalized-datasets`에 두며 안정 ID, 본문 hash, 원본 archive/entry, source URL, 문서 유형, locale, annotation을 기록한다. 변환 후 JSON 구문, 필수 필드, ID 유일성, 본문 hash, manifest hash를 전수 검사한다.

형식 확인, 변환 상태 분류, 건수 집계는 결정적 스크립트로 자동 처리하고 개발자가 manifest와 표본을 확인한다. 이 단계에는 생성형 AI, 외부 LLM, 임베딩, 의미 분류를 사용하지 않는다.

정규화 성공은 검색 승인을 의미하지 않는다. 모든 공개 데이터셋 출력은 기본적으로 `needs_review`이며 라이선스, 개인정보, 파싱 품질, 중복, 현재 버전을 검토한 뒤에만 `approved_for_search`로 승격한다.

한국어 약관 조항화는 다음 명령으로 별도 실행한다.

```powershell
.\scripts\Process-PublicCorpus.ps1
```

이 단계는 정규식 조 번호, Unicode 정규화, 정확 포함, 문자 5-gram overlap만 사용한다. 생성형 AI나 의미 판단은 사용하지 않으며 결과는 `.artifacts\processed-corpus`에 `needs_review`로 남는다. 자동 연결되지 않은 annotation과 비정상 문서 구조는 `review-queue.jsonl`에 기록한다.

사람 검토용 표본은 `New-PublicCorpusReviewPacket.ps1`로 생성한다. 패킷은 source와 품질 유형별로 결정적 표본을 뽑고 reviewer가 작성할 상태 열을 빈 값으로 둔다. 패킷의 `candidate_for_search`는 검토 후보 표시일 뿐 registry 승인, RAG 적재, Git 공개를 자동 수행하지 않는다.

검토 결과는 `Validate-PublicCorpusReview.ps1`로 검증한다. source-level 이용 조건 허용과 item-level privacy/parse 통과가 동시에 있어야 pending import 후보가 된다. `Import-ReviewedPublicCorpus.ps1`은 기본 dry-run이며 `-Apply`를 명시해도 `pending_review` version만 생성한다. 최종 `approved_for_search`는 기존 audit 명령에서 별도로 기록해야 한다.

## Search Review Decisions

검색 승인 결정은 개별 document version에 대해 명시적으로 기록한다.

```powershell
.\scripts\Review-TermsDocument.ps1 `
  -VersionId <version-id> `
  -Decision approved_for_search `
  -Reviewer <reviewer> `
  -Reason "검토한 항목과 판단 근거"
```

허용 결정은 `approved_for_search`, `rejected_license`, `rejected_privacy`, `rejected_quality`, `deprecated`다. reviewer와 reason은 비어 있을 수 없고 모든 결정은 `terms_review_events`에 시각과 함께 저장된다. pending, rejected, deprecated 및 과거 version은 검색 table에 포함되지 않는다. 검색 승인은 공개 fixture 재배포 승인을 의미하지 않는다.

## Required Source Metadata

Every consent case must include:

- `capture_method`: `manual_synthetic`, `manual_field_observation`, `user_submitted_screen`, or `user_submitted_text`.
- `artifact_type`: `text_only`, `redacted_text_only`, `redacted_screenshot`, or `synthetic_screen`.
- `redaction_status`: `not_required`, `pending_review`, or `redacted`.
- `review_status`: `not_required`, `pending_review`, `approved`, or `rejected`.
- `public_fixture_allowed`: must be `true` for cases stored in this repository.
- `contains_raw_screenshot`: must be `false`.
- `contains_ocr_text`: may be `true` only for redacted OCR text.
- `raw_artifact_in_repo`: must be `false`.

`synthetic` cases use `not_required` redaction and review status. `field_candidate` and `captured_redacted` cases must be `redacted` and `approved` before they are added.

Every dataset must also include top-level version metadata:

- `dataset_schema_version`
- `dataset_version`
- `label_rubric_version`
- `rule_set_version`

Risk and direction labels must follow `docs/LABELING_GUIDE.md`.

## Validation Rules

The API loader rejects consent fixtures when:

- Case IDs or element IDs are duplicated.
- `recommended_goal_id` is not in the goal catalog.
- `locale` is not `ko-KR`.
- Required display fields are blank.
- Overall expected risk does not match the highest expected element risk.
- Any raw artifact is marked as stored in the repository.
- A non-synthetic case is not redacted and approved.
- Public fixture notes contain URL-like, email-like, or phone-like text.

These checks are intentionally conservative. If they block a useful case, adjust the policy and validator together so future data remains auditable.

## Next Dataset Targets

- Add more medium-risk cases so the rule path is not only low/high.
- Add negative examples where scary-looking text is not actually a user-goal conflict.
- Add provider/app category tags only after redaction, not as personally identifying source labels.
- Keep deterministic rule calibration separate from future provider/OCR evaluation.
