# Handoff

## Current State

- Work is isolated under `C:\Users\kll45\OneDrive\바탕 화면\exitguide`.
- Raw and generated dataset artifacts stay under `.artifacts` or the explicitly documented Downloads inputs.
- The API and mobile app pass local checks.
- The latest transfer archive is written to `.artifacts\exitguide-source.zip`.
- The latest deterministic demo report is written to `.artifacts\demo-report.md`.
- The demo report now ends with a Quality Gate section and fails generation if scenario, synthetic upload, or consent-case rule calibration drifts.
- The latest API schema export is written to `.artifacts\openapi.json`.
- GitHub Actions workflow scaffold: `.github\workflows\exitguide-checks.yml`.
- Current structure assessment: `docs\ARCHITECTURE_REVIEW.md`.
- Git/GitHub local workflow notes: `docs\GIT_WORKFLOW.md`.
- Self-diagnosis checklist: `docs\SELF_DIAGNOSIS.md`.
- Consent/terms data collection policy: `docs\DATA_COLLECTION_POLICY.md`.
- Public terms/privacy dataset inventory and collection result: `docs\PUBLIC_DATASET_INVENTORY.md`.
- Consent/terms labeling rubric: `docs\LABELING_GUIDE.md`.

## Most Important Commands

```powershell
.\scripts\Test-All.ps1
.\scripts\Test-ApiUnit.ps1
.\scripts\Test-AndroidConfig.ps1
.\scripts\Test-MobileAudit.ps1
.\scripts\Test-WebDemo.ps1
.\scripts\Test-CiWorkflow.ps1
.\scripts\Test-GitHubTooling.ps1
.\scripts\Test-OpenApi.ps1
.\scripts\Test-DocsSync.ps1
.\scripts\Test-ProviderConfig.ps1
.\scripts\Test-MobileFallbackCatalog.ps1
.\scripts\Test-MobileTraceDisplay.ps1
.\scripts\Test-MobileApiUrl.ps1
.\scripts\Test-MobileHistoryDedupe.ps1
.\scripts\Test-MobileReadinessDetails.ps1
.\scripts\Test-MobileSelectionClear.ps1
.\scripts\Test-TestEnvironment.ps1
.\scripts\Test-TextHygiene.ps1
.\scripts\Test-ArchiveSafety.ps1
.\scripts\Test-ProjectStatus.ps1
.\scripts\Complete-WorkBlock.ps1 -Label <label>
.\scripts\Build-TermsCorpus.ps1
.\scripts\Build-CollectionRegistry.ps1
.\scripts\Collect-PublicDatasets.ps1
.\scripts\Convert-PublicTermsDatasets.ps1
.\scripts\Process-PublicCorpus.ps1
.\scripts\New-PublicCorpusReviewPacket.ps1
.\scripts\Validate-PublicCorpusReview.ps1
.\scripts\Import-ReviewedPublicCorpus.ps1
.\scripts\Import-TermsCaptures.ps1 -InputPath <capture-json-or-folder>
.\scripts\Review-TermsDocument.ps1 -VersionId <id> -Decision <decision> -Reviewer <name> -Reason <reason>
.\scripts\Export-OpenApi.ps1
.\scripts\Start-DevServers.ps1
.\scripts\Start-WebDemo.ps1
.\scripts\Start-JudgeDemo.ps1
.\scripts\Start-TestEnvironment.ps1
.\scripts\Get-DevUrls.ps1
.\scripts\Get-ProjectStatus.ps1
.\scripts\New-DevBranch.ps1 -BranchName codex/<name>
.\scripts\New-WorkBlockArchive.ps1 -Label <label>
.\scripts\New-TransferArchive.ps1
.\scripts\Publish-GitHub.ps1 -RepositoryName exitguide -Visibility private
.\scripts\Stop-DevServers.ps1
.\scripts\Stop-TestEnvironment.ps1
.\scripts\Build-AndroidLocal.ps1
```

## Demo Surface

- Phone demo: ten deterministic API demo scenarios.
- Mobile app: Korean-first tab layout with one purpose input, automatic goal inference, APK overlay controls, and compact API state.
- First screen keeps the AI/API settings panel visible so phone users can enter API URL, provider, API key, model, and base URL without hunting through hidden controls.
- App provider selection: server default, Google Gemini, OpenAI GPT, and EXAONE can be chosen in the phone UI and sent with each analysis request.
- Flow demo: cancellation, trial, add-on, and account-deletion paths.
- Solar demo workflows: `GET /v1/solar-demo-workflows` exposes six saved Solar Pro 3 workflow outputs built from Korean Consumer Agency standard consultation cases for cancellation, refund, cooling-off, and excessive-penalty demos.
- Screenshot: single-screen upload analysis.
- Screenshot flow: 2-6 screenshot sequence upload.
- Analysis and flow responses include deterministic trace IDs for matching mobile/web output to demo reports.
- Recent analyses and recent flows persist locally on the device.
- Web demo: `apps\web-demo` can render scenario, prompt preview, flow, and synthetic upload calibration outputs from a desktop browser.
- Web demo smoke tests also guard the first-screen UI against oversized rectangular radii, negative letter spacing, and decorative radial backgrounds.
- Web demo accessibility checks guard status/result live regions, URL input behavior, focus-visible states, and dynamic button types.
- Live test environment: `scripts\Test-TestEnvironment.ps1` starts API/web demo services, verifies live HTTP API flows and web loading, then stops only the processes it started.
- Readiness check: `GET /v1/readiness` summarizes demo-critical catalog/provider/flow-upload checks, validates catalog references, and verifies the synthetic manifest matches the PNG fixture folder.
- Quality gate: `GET /v1/demo-quality` centralizes readiness plus scenario, flow risk-path, and synthetic calibration and is surfaced in web/mobile demo status.
- Consent case dataset: `GET /v1/consent-cases` exposes 14 curated Korean terms/consent cases with source/provenance/version metadata, and `GET /v1/consent-cases/quality` checks deterministic rule calibration plus warning-level coverage targets before adding more real redacted captures.
- Solar workflow fixture: `fixtures\solar-demo-workflows\workflows.json` stores the sanitized Solar Pro 3 demo workflow results without API keys, raw request payloads, or raw source archives.
- Terms corpus: `GET /v1/terms-corpus`, `GET /v1/terms-corpus/search`, and `GET /v1/terms-corpus/quality` provide the seed backend path for terms collection, local retrieval, RAG preparation, and future non-LLM rule experiments.
- Terms corpus build: `scripts\Build-TermsCorpus.ps1` regenerates `.artifacts\terms-corpus.sqlite` from `fixtures\terms-corpus\documents.json`, including normalized chunk, signal, tag, and FTS5 search tables.
- Terms capture import: `scripts\Import-TermsCaptures.ps1` imports OpenClaw/manual JSON captures into `.artifacts\terms-corpus.sqlite`, records them as `pending_review`, deduplicates exact content, and excludes them from retrieval until explicit approval.
- Terms review gate: `scripts\Review-TermsDocument.ps1` records audited approval/rejection decisions; only current `approved_for_search` versions are rebuilt into FTS/search tables.
- Public corpus processing: `scripts\Process-PublicCorpus.ps1` classifies all known source roles and deterministically sections AI Hub/FTC Korean terms into `.artifacts\processed-corpus`, with quality reports and review queues. It performs no AI analysis and no search approval.
- Public review packet: `scripts\New-PublicCorpusReviewPacket.ps1` creates a deterministic 143-item human checklist under `.artifacts\review-packets\public-corpus-v1`; all review and approval fields remain blank.
- Public review validation: `scripts\Validate-PublicCorpusReview.ps1` validates item/source decisions and currently reports 143 pending, 0 completed, and 0 importable items.
- Reviewed public import: `scripts\Import-ReviewedPublicCorpus.ps1` defaults to dry-run; `-Apply` writes only pending versions and never changes search approval.
- Public dataset collection: `scripts\Collect-PublicDatasets.ps1` reads `fixtures\public-datasets\sources.json`, downloads directly accessible public terms/privacy datasets to `.artifacts\public-datasets\raw`, writes collection manifests under `.artifacts\public-datasets\results`, and leaves raw files out of Git.
- Collection registry: `GET /v1/collection-registry` and `GET /v1/collection-registry/quality` provide the seed service inventory, public document-source registry, manual cancellation-flow skeleton, and review-task queue for the OpenClaw/GLM collection workflow.
- Navigation vertical slice: `GET /v1/navigation/routes` and `POST /v1/navigation/guide` match AccessibilityService-style screen elements to a semantic route, keep every click with the user, recover from a route detour, and attach Terms corpus evidence at cancellation confirmation. The browser simulator is `apps/web-demo/navigation.html`.
- Universal Navigation Agent: `POST /v1/navigation/agent/observe` maps a purpose to a terminal function and performs user-started, low-risk exploration when no verified app/version route exists. New paths remain `shadow`; an independently reviewed `verified_candidate` may automatically reuse at most two safe intermediate clicks, while a semantic mismatch invalidates it within two observations and returns to generic exploration. Final and state-changing actions are never automated. `GET /v1/navigation/functions` exposes the versioned semantic function catalog, `GET /v1/navigation/agent/graph` exposes the learned app graph summary, and `GET /v1/navigation/agent/performance` reports separated real-device/synthetic TCD metrics. Android finalizes display-side TCD through `POST /v1/navigation/agent/performance/complete`.
- Public APK backend: `scripts\Deploy-PublicNavigationApi.ps1` deploys the committed API to the shared competition server, keeps K-EXAONE credentials server-side, and exposes it through HTTPS. The APK refreshes address rotations from `deploy/mobile-runtime.json`, so normal users need only the APK and internet access. Operations and the 2026-08-14 server limit are documented in `docs\PUBLIC_APK_DEPLOYMENT.md`.
- Dark Pattern MVP: `POST /v1/dark-pattern/inspect` reuses the existing goal-aware judgment, risk scoring, and Proof Card engine. `apps/web-demo/dark-pattern.html` shows the actual synthetic screen, highlights risky/safe choices, and supports interactive add-on or consent toggles. Navigation responses include the same analysis in `dark_pattern`.
- Collection registry build: `scripts\Build-CollectionRegistry.ps1` regenerates `.artifacts\collection-registry.sqlite` from `fixtures\collection-registry\registry.json`, including service, alias, platform, document-source, flow, flow-step, and review-task tables.
- Work-block snapshots: `scripts\New-WorkBlockArchive.ps1` writes timestamped zip snapshots under `.artifacts\work-blocks` when Git is unavailable.
- Project status: `scripts\Get-ProjectStatus.ps1` summarizes Git availability, latest artifacts, quality result, recent work-block snapshots, and currently detected local demo services.
- Local Git helper: `scripts\New-DevBranch.ps1` creates a `codex/` branch when Git is installed and the folder is a repository.
- Safe block completion: `scripts\Complete-WorkBlock.ps1` runs the quality gate, checks `git diff --check`, refreshes the transfer archive, writes a work-block snapshot, and prints project/Git status.
- CI scaffold: `.github\workflows\exitguide-checks.yml` runs the Windows bootstrap/check flow on push or pull request after the project is published to GitHub.
- CI caching: the workflow caches `.tools` and `apps\mobile\node_modules` so repeated GitHub runs do less bootstrap work.
- GitHub publishing: `scripts\Publish-GitHub.ps1` creates/uses a GitHub repo through `gh`, pushes the default branch, and can open a draft PR for a `codex/` branch after `gh auth login`.
- API unit checks: `scripts\Test-ApiUnit.ps1` verifies rule-engine risk scoring, signals, recommendation behavior, consent dataset integrity, and validator rejection behavior.
- Android config checks: `scripts\Test-AndroidConfig.ps1` verifies Expo asset paths, package name, SDK baseline, and EAS APK/App Bundle profiles.
- Mobile audit checks: `scripts\Test-MobileAudit.ps1` reports all npm advisories and fails only on critical findings with `npm audit --audit-level=critical`.
- Offline check option: `scripts\Test-All.ps1 -SkipMobileAudit` keeps deterministic local checks available when npm audit cannot reach the registry.
- CI workflow validation: `scripts\Test-CiWorkflow.ps1` parses the workflow and is wired into `scripts\Test-All.ps1`.
- OpenAPI validation: `scripts\Test-OpenApi.ps1` checks required paths/schemas after `scripts\Export-OpenApi.ps1`.
- Documentation sync: `scripts\Test-DocsSync.ps1` ensures API docs and handoff route lists match the FastAPI OpenAPI surface.
- API contract field sync: the same docs check also verifies key analysis and flow response fields are documented.
- Provider config checks: `scripts\Test-ProviderConfig.ps1` keeps `.env.example`, provider docs, and provider-readiness missing-env notes aligned.
- EXAONE-compatible providers: `OCR_PROVIDER=exaone_vision` and `LLM_PROVIDER=exaone` use the shared `EXAONE_*` configuration, while `mock` remains the deterministic baseline.
- Google Gemini providers: app provider `google` or server providers `gemini_vision`/`gemini` use `GOOGLE_*` and `GEMINI_MODEL`.
- OpenAI GPT providers: app provider `gpt` or server providers `openai_vision`/`openai` use `OPENAI_*`.
- Provider HTTP errors now surface concise upstream status/body details in the phone UI, which helps diagnose invalid keys, unavailable models, quota, or billing setup.
- Mobile fallback catalog sync: `scripts\Test-MobileFallbackCatalog.ps1` ensures the offline mobile catalog keeps the same IDs and references as the API catalog.
- Mobile trace display: `scripts\Test-MobileTraceDisplay.ps1` keeps trace IDs visible in mobile results, history, and Proof Card sharing.
- Mobile API URL checks: `scripts\Test-MobileApiUrl.ps1` keeps phone-friendly API URL normalization wired into input, persistence, and requests.
- Mobile history dedupe: `scripts\Test-MobileHistoryDedupe.ps1` keeps repeated trace IDs from creating duplicate recent-result cards.
- Mobile readiness details: `scripts\Test-MobileReadinessDetails.ps1` keeps failed setup/readiness details visible in the mobile API panel.
- Mobile selection clear: `scripts\Test-MobileSelectionClear.ps1` keeps selected screenshot and flow media clear actions wired.
- Test environment startup: `scripts\Start-TestEnvironment.ps1` launches API on `0.0.0.0:8010`, web demo on `127.0.0.1:8020`, and optional Expo Metro via `-IncludeMobile`, with tracked PIDs for teardown.
- Text hygiene: `scripts\Test-TextHygiene.ps1` catches known mojibake/replacement characters before they reach demo UI or docs.
- Archive safety: `scripts\Test-ArchiveSafety.ps1` verifies source archive validation rejects excluded directories, raw/private capture paths, `.env` files, private keys, and sensitive-looking token contents.
- Project status validation: `scripts\Test-ProjectStatus.ps1` ensures `scripts\Get-ProjectStatus.ps1` keeps reporting artifact, service, and Git block details.
- Dev startup: `scripts\Start-DevServers.ps1` waits for `/v1/demo-quality` and the Expo Metro port before printing URLs.
- Judge demo startup: `scripts\Start-JudgeDemo.ps1` waits for `/v1/demo-quality` and the web demo page before printing URLs.
- Self-diagnosis details: `docs\SELF_DIAGNOSIS.md` explains every local quality gate.

## API Surface

- `GET /health`
- `GET /v1/status`
- `GET /v1/providers`
- `GET /v1/readiness`
- `GET /v1/demo-quality`
- `GET /v1/goals`
- `GET /v1/demo-scenarios`
- `GET /v1/demo-flows`
- `GET /v1/solar-demo-workflows`
- `GET /v1/synthetic-screens`
- `GET /v1/consent-cases`
- `GET /v1/consent-cases/quality`
- `GET /v1/terms-corpus`
- `GET /v1/terms-corpus/search`
- `GET /v1/terms-corpus/quality`
- `GET /v1/collection-registry`
- `GET /v1/collection-registry/quality`
- `GET /v1/navigation/routes`
- `GET /v1/navigation/functions`
- `GET /v1/navigation/agent/graph`
- `GET /v1/navigation/agent/performance`
- `GET /v1/navigation/gold/recordings/{recording_id}`
- `POST /v1/prompt/demo`
- `POST /v1/analyze`
- `POST /v1/analyze/demo`
- `POST /v1/analyze/flow`
- `POST /v1/analyze/flow/upload`
- `POST /v1/navigation/guide`
- `POST /v1/navigation/agent/observe`
- `POST /v1/navigation/agent/performance/complete`
- `POST /v1/navigation/gold/recordings/{recording_id}/complete`
- `POST /v1/navigation/gold/recordings/{recording_id}/review`
- `POST /v1/navigation/gold/recordings/{recording_id}/cancel`
- `POST /v1/dark-pattern/inspect`

## Best Next Steps

1. Review representative normal/error samples from the AI Hub and FTC review queues and structure license/privacy decisions.
2. Promote a small reviewed Korean corpus through the audited approval path without bulk auto-approval.
3. Connect approved public sections to the operational SQLite corpus while preserving source/version/hash provenance.
4. Create the first independent retrieval gold set and record a lexical FTS5 baseline before vector RAG or bulk LLM parsing.

See `docs\ROADMAP.md` for phase boundaries and completion criteria. The mobile/judge demo remains available, but UI polish is not the current priority.
