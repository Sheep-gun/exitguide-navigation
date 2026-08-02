# Development Log

## 2026-08-01 — 앱·버전 한정 검증 후보 경로 재사용

- 새 탐색 경로는 계속 `shadow`로 저장하고, 독립적인 목적지·안전 검증을 통과한 경로만 `verified_candidate → verified`로 승격하도록 생명주기를 분리했다. 정식 `trusted` 승격은 충분한 반복 성능 표본 없이는 수행하지 않으며 어느 등급도 클릭 배열 재생 권한을 갖지 않는다.
- 같은 앱 패키지·버전·locale·최종 기능에서 시작 화면과 각 전환의 의미 구조가 일치할 때만 검증 후보를 사용한다. 표시·활성·클릭 가능·저위험·비체크·비입력 중간 메뉴만 자동 실행하며 최종 토글과 상태 변경은 사용자에게 남긴다.
- 예상 버튼이나 전환 화면이 달라지면 최대 두 번의 관찰 안에 후보를 `stale`로 무효화하고, 같은 세션에서 범용 기능 그래프 탐색으로 복귀하도록 했다.
- 성공 실기기 세션의 클릭·Back·목적지 정지를 순서대로 복원하는 명시 검토 도구를 추가했다. 이 도구는 확인 문구 없이는 실행되지 않고 후보를 정식 승인하지 않는다.
- 과거 클라이언트가 앱 버전을 비워 보낸 경우에는 깨끗한 성공 세션에 한해 독립 확인한 버전을 한 번만 채울 수 있게 했다. 기존 비어 있지 않은 버전은 덮어쓸 수 없고, 버전이 없는 경로는 검증 후보가 될 수 없다.
- Android 11+ 패키지 가시성 때문에 활성 대상 앱 버전이 빈 값으로 전송되던 문제를 막기 위해 현재 사이드로드 대회 APK에 `QUERY_ALL_PACKAGES`를 추가했다. 이 권한은 활성 접근성 루트의 버전 확인에만 쓰며 앱 목록을 외부로 전송하지 않는다.
- 배민 알림 설정 semantic fixture를 37개 오프라인 사례(기본 1개, UI·상태·그래프·안전 변형 36개)로 확장했다. 전체 성공률 100%, 위험 자동 클릭·최종 자동 클릭·오목적지·오안내 0건을 확인했다.
- 정상 검증 후보 재사용은 자동 클릭 2회, 스크롤 0회, Back 0회, 예상 목적지 시간 5.1초였다. 오래된 경로는 한 번의 관찰 안에 무효화·fallback했고, 앱 버전이 다르면 후보를 사용하지 않았다.

## 2026-07-28 — 안전 우선 탐색 시간 최적화

- 플로팅 시작 버튼부터 최종 목적지 확정까지의 TCD를 Android와 API에서 함께 계측한다.
- 서버, K-EXAONE, DB, 화면 분석, OCR, 자동 조작, UI 안정화, 외부 앱 대기 시간을 분리했다.
- `navigation_sessions`, `navigation_stage_timings`, `graph_edge_performance`, `route_performance`, `app_version_signatures`, `route_rankings`를 기존 그래프 SQLite에 추가했다.
- 오답·위험 경로를 먼저 제외하고 현재 앱 버전의 반복 성공률, TCD p90·p50, 상호작용 비용 순으로 경로를 정렬한다.
- Gym에 콜드/웜 TCD, 10·30·60초 내 성공률, 캐시 시간 단축률과 앱·목적별 최단 안전 경로를 추가했다.
- 개인정보 필드를 거부하는 실제 기기 성능 로그 검사·가져오기 도구를 추가했다.
- K-EXAONE은 계속 의미 판정과 검토 제안만 담당하며 성능 수치나 정답을 생성하거나 DB를 자동 수정하지 않는다.

## 2026-07-28 — Navigation DB Gym

- 검토 가능한 JSON 기능 사전과 자동 재생성되는 SQLite 런타임 인덱스를 연결했다.
- 자연어 목적 조합 규칙, 기능 별칭, 긍정·부정 문맥, 공통 관문 그래프를 catalog v1.5.0에 반영했다.
- development, frozen holdout, adversarial, real-device-gold 분할을 추가했다.
- 47개 목적 전체를 대상으로 언어·역할·순서·유사 메뉴를 변형하는 full generator와 빠른 회귀 세트를 추가했다.
- Top-1, 목적지, 안전 정지, 위험/오클릭, 상호작용 비용, 지연, 경로 재사용, 커버리지를 측정하고 실패 유형별 변경 후보를 생성한다.
- K-EXAONE은 hard case의 검토 후보만 제안하며 benchmark 정답이나 DB를 자동 수정하지 못하도록 제한했다.
- 최종 상태 변경 버튼은 계속 사용자만 누르며 위험 자동 클릭 gate는 0%로 고정했다.

## 2026-07-14 Public Terms Dataset Normalization

- Added modular streaming adapters for AI Hub 019 XML/JSON pairs and the Open Terms Archive contrib ZIP without extracting or modifying the originals.
- Normalized and validated all 9,000 AI Hub terms documents, preserving advantageous/disadvantageous labels, raw category metadata, archive provenance, stable IDs, and content hashes.
- Recovered 162 malformed AI Hub source files through declaration repair, tolerant pseudo-XML parsing, and one plain-text fallback without dropping records.
- Selected and normalized the latest service/document-type version from 41,883 Open Terms Archive Markdown revisions: 874 documents across 383 services.
- Added reusable full-JSONL validation for required fields, unique IDs, text hashes, manifest counts, and output hashes; conversion reports remain under `.artifacts/normalized-datasets` with `needs_review` status.
- Left the 3.14GB Princeton-Leuven SQLite XZ source untouched pending schema and decompressed-size planning; the next block is clause segmentation plus the approval-only search gate.

## 2026-07-08 Public Dataset And Solar Demo Workflow

- Shifted the project priority toward backend data groundwork: public terms/privacy datasets, consumer guidance data, and repeatable collection records.
- Added a public dataset inventory and collector flow that keeps raw source material outside Git under `.artifacts/public-datasets`, while tracking only source metadata, collection scripts, and documentation.
- Collected directly accessible public datasets for terms/privacy/consumer guidance, including Korea FTC standard terms attachments, Korea Consumer Agency standard consultation answers, ToS;DR/Zenodo, Hugging Face online terms of service, UsablePrivacy corpora, PrivacyQA, and related metadata sources.
- Recorded access boundaries: AI Hub and Kaggle require user/account-side collection, while Common Crawl, Princeton-Leuven, and Open Terms Archive should be handled as targeted large-scale sources rather than full immediate mirrors.
- Selected the Korea Consumer Agency standard consultation answers as the first practical demo dataset because it is Korean, CSV-based, cancellation/refund-oriented, and directly aligned with ExitGuide's user-goal workflow.
- Added a Solar Pro 3 workflow runner that turns selected consumer guidance cases into ExitGuide-style step-by-step demo analyses: user goal, screen text, risk signal, guidance summary, recommended action, evidence quotes, and workflow steps.
- Stored the Upstage key only in local `.env`, kept it out of Git, and verified the Solar Pro 3 run against six cases after fixing `.env` formatting.
- Saved the Solar workflow outputs as sanitized demo fixtures under `fixtures/solar-demo-workflows/workflows.json`, excluding API keys, authorization headers, raw request payloads, and raw source archives.
- Added `GET /v1/solar-demo-workflows`, schema models, loader validation, API unit coverage, and documentation so the saved Solar results are now part of the backend demo surface.
- Verified the block with API unit checks, docs sync, API smoke, OpenAPI export/check, PowerShell syntax checks, text hygiene, archive safety, and whitespace checks.
- Next backend direction: normalize collected datasets into SQLite, build a safer public-dataset ingestion layer, convert/parse HWP/HWPX/PDF public terms where useful, and connect the saved Solar workflows into mobile/web demo presentation.

## 2026-05-10 Purpose Platform And Overlay

- Added phone-side provider settings for server default, Google Gemini, OpenAI GPT, and EXAONE.
- Added request-time provider fields so screenshot, flow, demo, and overlay analysis can carry a provider ID, API key, model, and base URL.
- Added Gemini and OpenAI vision OCR plus LLM providers, alongside the existing EXAONE-compatible providers.
- Added `/v1/providers` and provider readiness coverage for Gemini/OpenAI/EXAONE.
- Aligned Gemini REST requests with Google's shell examples for image parts, system instructions, and JSON response mode.
- Added Gemini response schemas and tolerant JSON extraction so OCR/LLM output still parses when the model wraps JSON in a code fence or short explanation.
- Added provider-error logging for handled 503 responses and Gemini fallback behavior so malformed OCR/LLM JSON no longer kills upload analysis.
- Generalized the second OCR pass into row-level mobile UI extraction for selectable rows, checkboxes, toggles, radio controls, monetary add-ons, and primary CTA buttons.
- Tightened rule overrides so selected optional rows conflict with goals that avoid optional consent/add-ons, while unselected optional rows stay low risk.
- Expanded provider errors so the phone can show concise Google/OpenAI/Friendli HTTP details instead of a generic unusable-response message.
- Raised remote provider timeouts for slower screenshot OCR plus judgment runs on real phones.
- Kept the mobile AI/API settings panel visible by default so API URL and Google/GPT/EXAONE key entry are always easy to find.
- Reworked the mobile app around one Korean purpose input, with all screenshot, flow, and demo analysis requests sending either `goal_text` or `infer_goal=true`.
- Added API-side goal resolution so custom purpose text maps to the nearest built-in rule set while preserving the user's own goal label in responses and EXAONE prompts.
- Added an Android overlay config plugin, native module, foreground service, screen-capture activity, and mobile controls for an APK-only floating `AI` icon that posts the current screen to `/v1/analyze`.
- Updated EXAONE defaults to Friendli Serverless OpenAI compatibility with `LGAI-EXAONE/K-EXAONE-236B-A23B`, while keeping mock providers as the no-key local baseline.
- Built a local release APK at `.artifacts\apk\exitguide-ai-overlay-release.apk` and verified overlay/media-projection permissions with `aapt`.
- Added `scripts\Build-AndroidLocal.ps1` to repeat local prebuild, Gradle assemble, and APK artifact copy when the Android SDK is installed under `.tools\android-sdk`.

## 2026-05-10 Mobile App Redesign

- Reworked the mobile app around one integrated analysis goal instead of separate scattered goal selection.
- Changed the mobile first-screen hierarchy to compact API state, integrated intent context, and Demo/Screenshot/Flow/History tabs.
- Translated mobile-facing labels, errors, result cards, risk badges, upload controls, and history surfaces into Korean.
- Reordered analysis and flow result views so the Proof Card appears before lower-level element details.
- Added a neutral mock OCR fallback for passive community/comment screenshots so unknown uploads no longer default to high-risk cancellation fixtures.
- Added EXAONE-compatible OCR and LLM providers with `EXAONE_*` configuration while keeping mock providers as the deterministic local baseline.
- Updated provider readiness, fallback catalog tests, trace tests, selection-clear tests, and API URL checks for the redesigned Korean surfaces.
- Ran `scripts\Test-All.ps1 -SkipExpoDoctor`; all checks passed.

## 2026-05-10 Overnight Build

- Restored the app inside `C:\Users\kll45\Desktop\exitguide` without modifying the original download files.
- Added project-local bootstrap checks, Pillow dependency, and regenerated Korean synthetic screenshots.
- Connected the mobile app to API-backed goals and demo scenarios with built-in fallback data.
- Added local analysis history with AsyncStorage and modular hooks for catalog, debounce, and history state.
- Split the result UI into reusable cards for risk badges, recommendations, UI elements, proof cards, and risk legend.
- Added Proof Card sharing through the native share sheet.
- Added API upload validation, provider readiness notes, and controlled LLM JSON parsing.
- Added goal alignment scoring and risk-count display to make the selected goal explicit in the UI.
- Added account deletion plus low-risk checkout/required-terms comparison scenarios from the proposal's validation direction.
- Expanded the generated synthetic fixture pack to 15 Korean screens for proposal/demo material.
- Added `scripts\New-DemoReport.ps1` to generate `.artifacts\demo-report.md` from live deterministic API scenarios.
- Added and smoke-tested `scripts\Start-DevServers.ps1` for background API + Expo startup with logs under `.logs`.
- Tightened `scripts\Stop-DevServers.ps1` so it only stops processes whose command line includes this project root.
- Reviewed `npm audit --omit=dev`; the current moderate findings are transitive Expo/PostCSS advisories and npm suggests a breaking Expo downgrade, so no forced audit fix was applied.
- Added `/v1/analyze/flow` as a controlled demo-flow API foundation for the later multi-screen roadmap.
- Added a mobile Flow demo section that calls `/v1/analyze/flow` and renders a flow-level Proof Card.
- Added `/v1/analyze/flow/upload` plus mobile multi-screenshot selection for real screenshot sequence analysis.
- Persisted the mobile API base URL with AsyncStorage so physical-phone testing survives app reloads.
- Added separate local flow history so multi-screen results can be reopened independently from single-screen analyses.
- Added an auto-generated synthetic screen `manifest.json` with category and expected-risk labels.
- Exposed the synthetic screen manifest through `GET /v1/synthetic-screens`.
- Added recognized-but-not-wired provider classes for NAVER CLOVA OCR, HyperCLOVA, and Upstage so configuration errors are explicit.
- Added `scripts\Test-All.ps1` to run API smoke, mobile typecheck, demo report generation, and optional Expo doctor.
- Added smoke-test guarding against legal-conclusion terms in demo analysis payloads.
- Promoted low-risk confirmation screens into API demo scenarios and expanded mobile flow demos across cancellation, trial, add-on, and account deletion paths.
- Expanded the generated demo report to include four flow checks, not only the add-on contrast.
- Added `/v1/prompt/demo` so the structured AI prompt can be inspected during demo preparation.
- Added expected fixture risk labels into `.artifacts\demo-report.md` for quick calibration checks.
- Tightened screenshot flow upload to require 2-6 screens, matching the multi-screen UX.
- Added aggregate risk counts to flow responses and mobile flow result cards.
- Hardened local history loading so older stored entries without alignment/risk-count fields are ignored safely.
- Added `docs\HANDOFF.md` with current commands, API surface, demo surface, and next steps.
- Added generated Expo icon, adaptive icon, and splash assets via `scripts\Generate-MobileAssets.py`.
- Added per-element rule signals to API responses and mobile element cards.
- Enabled permissive CORS for local MVP browser and tooling demos.
- Added a dependency-free static web demo under `apps\web-demo` plus `scripts\Start-WebDemo.ps1`.
- Added `scripts\Test-WebDemo.ps1` and wired it into `scripts\Test-All.ps1`.
- Added synthetic upload calibration buttons to the web demo for quick desktop rehearsal.
- Added prompt previews and request loading/error states to the web demo.
- Made the web demo auto-load the local catalog and distinguish readiness warnings visually.
- Added `scripts\Start-JudgeDemo.ps1` for one-command API + web-demo rehearsal.
- Added `GET /v1/readiness` and surfaced readiness chips in both the mobile app and web demo.
- Added `GET /v1/demo-flows` and moved mobile/web flow cards onto the API-backed catalog with local fallbacks.
- Polished mobile flow UX with overflow thumbnails and stale-result clearing while new analyses run.
- Added a mobile API URL reset control for quick recovery after laptop/IP changes.
- Added mobile prompt previews for deterministic demo runs so judges can inspect the controlled JSON prompt from the app.
- Added `scripts\Export-OpenApi.ps1` and wired OpenAPI artifact generation into `scripts\Test-All.ps1`.
- Tuned mock OCR fixture inference so all 15 synthetic screenshot filenames map to calibrated high/medium/low upload results.
- Expanded `.artifacts\demo-report.md` with a synthetic upload calibration table.
- Added API-backed goal descriptions so the mobile goal selector is not dependent on fallback copy.
- Added flow `risk_path` output and rendered it in mobile, web demo, smoke tests, and demo report.
- Cleaned Android/setup docs so commands point at the isolated desktop workspace and include the judge-demo path.
- Updated the demo script around readiness chips, risk paths, and synthetic upload calibration.
- Added `scripts\Build-AndroidPreview.ps1` as a guarded wrapper for the future EAS APK build.
- Added `scripts\Test-Scripts.ps1` and wired PowerShell syntax validation into `scripts\Test-All.ps1`.
- Added `recommended_goal_id` to the synthetic screen manifest and removed duplicated category-to-goal mappings from tests/web demo.
- Updated bootstrap to run the broader local check suite and print the judge-demo starter.
- Added friendlier bootstrap-required errors to API/mobile start and check scripts.
- Wrapped the mobile app in an error boundary so unexpected UI failures show a reset path instead of a blank screen.
- Added an explicit `npm run typecheck` script and wired `scripts\Typecheck-Mobile.ps1` through it.
- Pointed the placeholder mobile `lint` script at typecheck so it no longer references an uninstalled ESLint setup.
- Added `docs\API_CONTRACT.md` for the current health, catalog, analysis, and flow endpoints.
- Re-ran the full bootstrap script successfully after the overnight changes.
- Created a fresh transfer archive at `.artifacts\exitguide-source.zip`.
- Ran `expo-doctor`; all 17 Expo project checks passed.
- Added a demo-report quality gate so scenario and synthetic upload risk calibration mismatches fail local checks.
- Polished mobile/web demo display separators to avoid fragile non-ASCII bullets in judge-facing UI text.
- Tightened web-demo checks against decorative radial backgrounds, negative letter spacing, and oversized rectangular radii.
- Refreshed `.artifacts\exitguide-source.zip` after the final quality-gate pass.
- Added `GET /v1/demo-quality` so readiness and risk calibration are available as a reusable API contract, not only a report-script check.
- Surfaced the demo-quality status in both the mobile API panel and the web demo readiness chips.
- Centralized API service exception translation in `app\http_errors.py` to reduce repeated route-level error mapping.
- Added `scripts\New-WorkBlockArchive.ps1` for timestamped block snapshots when Git branching is not available on the machine.
- Expanded the demo-quality gate to verify deterministic flow overall risk and ordered `risk_path` calibration.
- Tightened readiness and API smoke checks so synthetic-screen manifest filenames must match the actual PNG fixture folder in both directions.
- Added `.github\workflows\exitguide-checks.yml` to run the Windows bootstrap/check flow on GitHub push and pull request.
- Added `scripts\Test-CiWorkflow.ps1` and wired it into `scripts\Test-All.ps1`.
- Added `scripts\Test-OpenApi.ps1` and wired it into `scripts\Test-All.ps1` so exported API contract artifacts are checked for required paths and schemas.
- Hardened frequently used PowerShell scripts with `Push-Location`/`Pop-Location` so manual runs do not leave the shell in a different project subdirectory.
- Reduced repeated mobile `HomeScreen` result-reset logic with shared helpers and cleared stale results before new single-screen analysis runs.
- Improved the web demo request helper so FastAPI error responses show the human-readable `detail` message instead of raw JSON.
- Updated `scripts\Test-WebDemo.ps1` to use an ephemeral local port so smoke tests do not accidentally pass against an already-running server on port 8020.
- Hardened `scripts\Start-JudgeDemo.ps1` to wait for the API demo-quality endpoint and web demo page before declaring the judge demo ready.
- Added `scripts\Get-ProjectStatus.ps1` to summarize Git availability, latest generated artifacts, quality result, and recent work-block snapshots.
- Added `docs\ARCHITECTURE_REVIEW.md` with the current structure judgment, completed architecture improvements, and next structural bets.
- Added `docs\GIT_WORKFLOW.md` and `scripts\New-DevBranch.ps1` to clarify GitHub plugin vs. local Git and support branch creation once Git is installed.
- Updated `scripts\Get-ProjectStatus.ps1` to call out that the GitHub connector can use a known `owner/repo` but does not provide local `git.exe`.
- Added `scripts\Test-TextHygiene.ps1` and wired it into `scripts\Test-All.ps1` to catch known mojibake/replacement characters in demo-facing source and docs.
- Added `scripts\Test-DocsSync.ps1` and wired it into `scripts\Test-All.ps1` so API docs and handoff route lists cannot drift from the FastAPI OpenAPI surface.
- Added `scripts\Test-MobileFallbackCatalog.ps1` and wired it into `scripts\Test-All.ps1` so offline mobile fallback IDs and references stay aligned with the API catalog.
- Cleared mobile catalog loading state when the API URL is blank so the API panel cannot stay in a stale loading state after reset.
- Split FastAPI routes into `app\routers\ops.py`, `app\routers\catalog.py`, and `app\routers\analysis.py` while keeping the public API contract unchanged.
- Tightened `/v1/analyze/flow` so deterministic demo flows require 2-6 screens, matching the upload flow contract.
- Hardened `scripts\Start-DevServers.ps1` to wait for API demo-quality readiness and the Expo Metro TCP port before printing demo URLs.
- Wrapped long-running API, mobile, and web-demo start scripts with `Push-Location`/`Pop-Location` cleanup.
- Replaced the rule-engine response tuple with a typed `ResponseParts` dataclass so analysis assembly uses named fields.
- Expanded API smoke coverage for recognized-but-unwired HyperCLOVA and Upstage provider readiness failure paths.
- Added flex-safe header spacing to mobile result and API status panels so long source labels do not collide with badges or spinners.
- Surfaced demo-quality scenario, flow, and synthetic pass counts directly in the web demo status line.
- Added `apps\api\tests\rules_unit.py` plus `scripts\Test-ApiUnit.ps1` and wired it into `scripts\Test-All.ps1` for rule-engine scoring and recommendation coverage.
- Extended OpenAPI validation to assert the documented `/v1/analyze/flow` scenario list range remains 2-6 items.
- Aligned mobile fallback goal and scenario copy with the API catalog and tightened fallback catalog checks to include labels and descriptions.
- Added `screen_count` and `highest_risk_screen_number` to flow responses and surfaced them in the mobile app, web demo, smoke checks, and demo report.
- Updated work-block archives so new snapshot zips use a stable `exitguide` root folder instead of an internal staging folder name.
- Wrapped `scripts\Bootstrap-Windows.ps1` in `Push-Location`/`Pop-Location` so failed setup runs do not strand the shell in a subdirectory.
- Added a mobile npm override for `postcss` 8.5.10 and refreshed `package-lock.json`, clearing the moderate npm audit finding without downgrading Expo.
- Expanded `docs\GIT_WORKFLOW.md` with a concrete Git for Windows install command and clone-vs-init guidance.
- Added API smoke coverage for uploads that exceed `MAX_UPLOAD_BYTES`.
- Excluded future `.git` metadata from transfer and work-block archives.
- Expanded text hygiene coverage to include root/app README files and `.env.example`.
- Cleared selected upload media when opening saved mobile analysis or flow history entries, preventing stale selections from mixing with recalled results.
- Added `scripts\Test-AndroidConfig.ps1` and wired it into `scripts\Test-All.ps1` to guard Expo assets, package name, SDK baseline, and EAS build profile shape.
- Removed an unused variable from `scripts\Stop-DevServers.ps1`.
- Allowed flow-upload thumbnails to wrap on narrow mobile screens.
- Added an immediate web-demo catalog loading state so stale status text is cleared while API requests are in flight.
- Extended Android config checks to verify generated app icon, adaptive icon, and splash image dimensions.
- Added `scripts\Test-MobileAudit.ps1` and wired it into `scripts\Test-All.ps1`; all npm advisories remain visible while critical findings block the quality gate.
- Included `.example` files in text hygiene extension filtering so `.env.example` is actually scanned.
- Added `-SkipMobileAudit` to `scripts\Test-All.ps1` for offline deterministic checks when npm audit cannot reach the registry.
- Extended `scripts\Get-ProjectStatus.ps1` to report whether the API quality endpoint, web demo, and Expo Metro port are currently detected.
- Updated laptop migration docs to include `.github/` as source and `.artifacts/` as generated output.
- Added accessibility state metadata to the shared mobile `ActionButton` for disabled and loading states.
- Updated the web demo smoke test to require the flow highest-risk screen display.
- Corrected API contract docs so demo-quality status explicitly includes flow calibration.
- Added a readiness catalog-integrity check for goal, scenario, flow, and synthetic fixture references.
- Added an API smoke assertion that the readiness response includes the `catalog_integrity` check.
- Added a Git for Windows `winget` install hint to `scripts\Get-ProjectStatus.ps1` when local `git.exe` is missing.
- Added an explicit `SyntheticScreenCatalog` type hint to the readiness catalog-integrity helper.
- Added a root `.editorconfig` so encoding, line endings, and indentation stay stable across machines.
- Added `.editorconfig` to text hygiene coverage.
- Added `.gitattributes` so future Git commits treat generated image and archive artifacts as binary.
- Added `.gitignore` to text hygiene coverage.
- Updated the README setup note to reflect that bootstrap manages project-local Node.js while Python 3 and Git remain the main machine-level prerequisites.
- Added post-compression archive validation so transfer and work-block zips fail if excluded dependency, artifact, log, or Git metadata paths slip in.
- Optimized transfer and work-block archive scripts to skip excluded directories during recursion instead of filtering them after traversal.
- Added `docs\SELF_DIAGNOSIS.md` to summarize the full local quality gate surface and offline/CI skip options.
- Added `.github/` to the README repository layout.
- Installed project-local portable MinGit under `.tools` and updated Git helper/status scripts to find it when Git is not on PATH.
- Updated `scripts\Bootstrap-Windows.ps1` to install project-local MinGit automatically when no system Git is available.
- Refreshed setup docs around project-local Node.js and MinGit bootstrap behavior.
- Added `scripts\ExitGuide.Common.psm1` to centralize Git discovery, source archive copying, archive validation, and path-safety checks.
- Refactored branch/status/archive scripts to use the shared PowerShell helper module.
- Added `scripts\Complete-WorkBlock.ps1` as a repeatable safe block-completion gate for tests, transfer archive refresh, work-block snapshots, and status output.
- Expanded `scripts\Get-ProjectStatus.ps1` with branch, commit, remote, and working-tree summaries.
- Added `scripts\Test-ProjectStatus.ps1` and wired it into `scripts\Test-All.ps1`.
- Added GitHub Actions caching for project-local tools and mobile dependencies, and tightened CI workflow validation around that cache step.
- Improved web-demo accessibility for status/result live regions, URL input behavior, focus-visible states, and dynamic button types.
- Expanded `scripts\Test-WebDemo.ps1` to guard those web-demo accessibility contracts.
- Added deterministic analysis and flow trace IDs to API responses, mobile/web result metadata, OpenAPI checks, smoke tests, and demo reports.
- Expanded documentation sync checks to verify that `docs\API_CONTRACT.md` documents key `AnalysisResponse` and `FlowAnalysisResponse` fields.
- Improved provider-readiness notes so missing real-provider setup names exact env vars.
- Added `scripts\Test-ProviderConfig.ps1` and wired it into `scripts\Test-All.ps1`.
- Added `git diff --check` to `scripts\Complete-WorkBlock.ps1` when Git is available.
- Set repository text line-ending policy to LF in `.editorconfig` and `.gitattributes` to reduce Windows/Git warning noise.
- Installed project-local portable GitHub CLI and added bootstrap support for it.
- Added `scripts\Publish-GitHub.ps1` for authenticated GitHub repo creation, default-branch push, branch push, and optional draft PR creation.
- Added `scripts\Test-GitHubTooling.ps1` and wired it into `scripts\Test-All.ps1`.
- Surfaced analysis and flow trace IDs in mobile result history and shared Proof Card output.
- Added `scripts\Test-MobileTraceDisplay.ps1` and wired it into `scripts\Test-All.ps1`.
- Hardened mobile API URL handling so scheme-less phone/LAN addresses are normalized before saving or sending requests.
- Added `scripts\Test-MobileApiUrl.ps1` and wired it into `scripts\Test-All.ps1`.
- Deduplicated mobile analysis and flow history by deterministic trace IDs so repeated demos update the latest card instead of cluttering history.
- Added `scripts\Test-MobileHistoryDedupe.ps1` and wired it into `scripts\Test-All.ps1`.
- Added failed-readiness detail lines to the mobile API status panel so provider/setup blockers are visible without opening logs.
- Added `scripts\Test-MobileReadinessDetails.ps1` and wired it into `scripts\Test-All.ps1`.
- Added clear controls for single screenshot and screenshot-flow selections in the mobile app.
- Added `scripts\Test-MobileSelectionClear.ps1` and wired it into `scripts\Test-All.ps1`.
- Added tracked live test environment scripts for API/web demo startup, HTTP validation, and teardown.
- Added `apps\api\tests\live_environment.py` plus `scripts\Test-TestEnvironment.ps1`, and wired the live environment gate into `scripts\Test-All.ps1`.
- Updated the live test environment API binding to `0.0.0.0:8010` so physical phones can reach the detected LAN URL.
- Switched the default Google provider model to `gemini-3-flash-preview` and normalized Gemini 3/preview Google base URLs from `/v1` to `/v1beta`.
- Expanded agreement-screen OCR and rule fixtures with public web-derived patterns for `전체동의`, `[선택]`, 프로모션, 광고성 정보 수신, 마케팅 활용, 선택 정보 포함, and 정보/이벤트 수신 rows.
- Added consent-case dataset provenance/version metadata and `docs\LABELING_GUIDE.md` so risk/direction labels have a stable rubric.
- Expanded the consent-case calibration set to 14 cases with medium-risk and false-positive guard examples.
- Added consent dataset negative unit checks for duplicate IDs, invalid goals/locales, risk mismatch, unsafe provenance, raw artifact flags, and note hygiene.
- Expanded the consent-case quality response with calibration summaries and warning-level coverage targets.
- Hardened source archive validation and added `scripts\Test-ArchiveSafety.ps1` to reject raw/private paths, `.env` files, private keys, and sensitive-looking token contents.
- Added a seed terms corpus under `fixtures\terms-corpus`, local lexical search endpoints, corpus quality coverage, and a SQLite builder for future RAG/local-rule experiments.
- Added an OpenClaw/manual terms capture importer that normalizes capture JSON, rejects obvious private-data candidates, deduplicates by content hash, stages import status in SQLite, and keeps real terms text in `.artifacts` until review.
- Hardened the terms importer after ChatGPT Pro macro review: imports now persist accepted source/version records across runs, reject non-captured/non-Korean captures, ignore imported `public_fixture_allowed`, strip URL query/fragment data, deduplicate exact content across runs, and build FTS5/tagged SQLite retrieval tables.
- Added a collection registry backend seed with service inventory, public document sources, manual cancellation-flow skeletons, review tasks, quality coverage, API endpoints, and a SQLite builder for the OpenClaw/GLM data-collection workflow.
- Reviewed the data plan against the live backend and found that bulk source adapters, an approval-only retrieval gate, and an independent retrieval evaluation set must come before vector RAG or large-scale LLM parsing.
- Reorganized the README, roadmap, architecture review, and handoff around the end-to-end data flow, current measurable state, and phase-specific completion criteria.
- Defined the two-repository team architecture: this repository owns Terms and final integration, while `exitguide-navigation` owns Android navigation; added a shared goal contract and separated Terms routes without changing public API paths.

## 2026-07-15 Public Dataset Normalization

- Added source-specific adapters for public-data CSV, JSONL, ZIP, HWP/HWPX, YAML, XML, HTML, and SQLite formats.
- Converted 18 full-text, clause, and Q&A outputs containing 660,055 staging records; all remain `needs_review` and are not part of RAG.
- Expanded the Princeton-Leuven 3.29GB XZ into a 48.2GB read-only SQLite artifact, then normalized 333,986 policy texts with 1,071,487 snapshot provenance records into a 4.0GB JSONL.
- Normalized MAPS 441,626 policy targets and 121 OPP-115 GDPR mapping rows, and profiled all 1,200,341 FSDK rows as non-RAG supporting data.
- Repaired the FTC HWP parser to skip fixed-width inline controls, then reprocessed all 81 HWP and 12 HWPX standard-terms attachments.
- Added deterministic source coverage and full JSONL validation reports. No generative AI, external LLM, embedding, semantic classification, or RAG ingestion was used in this work block.
- Recorded processing as script-based automatic conversion followed by developer confirmation of manifests, counts, formats, and representative samples.

## 2026-07-15 국내 약관 조항화와 검색 승인 Gate

### 작업 목적과 판단 경계

이번 블록의 목적은 정규화된 자료를 바로 RAG에 넣는 것이 아니라, 자료의 역할을 먼저 분리하고 AI Hub·공정위 한국어 약관을 검토 가능한 조항 단위로 만드는 것이었다. 검색 승인 여부는 코드가 대신 판단하지 않았다. 생성 결과는 모두 `needs_review`이며 실제 공개 자료를 자동으로 `approved_for_search`로 바꾸지 않았다.

다운로드 자료는 모두 같은 종류가 아니므로 두 축으로 분류했다.

- `source_kind`: 약관 전문, 기존 조항/segment, 상담 사례, Q&A, metadata index, 보조자료
- `processing_role`: corpus 후보, annotation 원천, 별도 supporting evidence, 평가 전용, 수집 seed, source metadata, RAG 제외

분류표는 `fixtures/public-datasets/processing-roles.json`에 두고 23개 인벤토리 소스와 Open Terms Archive 전체본 1개의 누락·중복·모순을 코드로 검사한다. 결과는 corpus 후보 12개, 별도 근거 2개, 평가 전용 2개, 수집 seed 4개, source metadata 4개, RAG 제외 2개다. 한 자료가 annotation과 corpus처럼 복수 역할을 가질 수 있어 합계는 소스 수보다 크다.

### 구현 내용

`Process-PublicCorpus.ps1`과 `public_corpus.py`를 추가했다. 입력은 기존 `.artifacts/normalized-datasets/<source-id>/documents.jsonl`이며 원본이나 정규화 staging은 수정하지 않는다.

1. 줄 시작의 `제1조`, `제 1 조`, `제2조의2`, 선택 제목 괄호를 정규식으로 찾는다.
2. 전문, 조항, 조 번호가 없는 전체 문서로 section을 나누며 원문 `start_offset`과 `end_offset`을 보존한다.
3. section ID와 SHA-256을 결정적으로 만들고 provenance, 원문 hash, 품질 flag를 함께 기록한다.
4. 중복 조 번호, 역순 조 번호, 조 번호 없음, 짧거나 긴 section, 큰 전문, 의심 Unicode를 집계한다.
5. AI Hub `clause_articles`는 NFKC 정규화와 공백·구두점 제거 후 정확 포함으로 먼저 연결한다.
6. 정확 연결이 안 된 40자 이상 표본은 문자 5-gram target recall 0.72 이상, 차점과 0.05 이상 차이일 때만 연결한다.
7. 점수가 낮거나 짧거나 후보가 애매하면 추정 연결하지 않고 `review-queue.jsonl`에 이유와 최고 점수를 기록한다.

초기 정확 포함만으로는 AI Hub 라벨 10,200개 중 1,735개만 연결됐다. OCR·띄어쓰기 차이에 대응하는 보수적 5-gram 규칙을 추가한 뒤 3,181개가 더 연결되어 총 4,916개가 연결됐다. 남은 5,284개는 낮은 점수 4,875개, 짧은 표본 403개, 애매한 후보 6개로 보류했다. 임계값은 아직 도메인 정답이 아니라 검토 대기열 생성 기준이며, retrieval gold label로 사용하면 안 된다.

### 실제 처리 결과

실행 명령:

```powershell
.\scripts\Process-PublicCorpus.ps1
```

최종 재실행 시간은 약 30.28초였다.

| 소스 | 문서 | section | 본문 문자 | review queue | section 파일 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 공정위 표준약관 | 93 | 1,703 | 647,734 | 12 | 3,068,960 bytes |
| AI Hub 019 약관 | 9,000 | 223,024 | 89,402,170 | 8,614 | 489,719,934 bytes |

공정위는 article 1,610개, preamble 88개, 조 번호가 없는 전체 문서 5개였다. AI Hub는 article 217,766개, preamble 5,077개, 전체 문서 181개였다. AI Hub 구조 flag는 중복 조 번호 문서 3,085건, 역순 조 번호 문서 2,709건, 짧은 section 4,874건, 긴 section 34건, 의심 Unicode section 4건이었다. 복수 약관이나 부가 조항을 합친 원문이 있어 flag 자체가 오류 확정은 아니며 사람 검토 우선순위다.

출력 위치:

- 역할 보고서: `.artifacts/processed-corpus/source-role-report.json`
- source manifest: `.artifacts/processed-corpus/<source-id>/manifest.json`
- section: `.artifacts/processed-corpus/<source-id>/sections.jsonl`
- 품질 집계: `.artifacts/processed-corpus/<source-id>/quality-report.json`
- 검토 대기열: `.artifacts/processed-corpus/<source-id>/review-queue.jsonl`

모든 출력 manifest에는 `ai_used: false`, `search_eligible: false`, `review_status: needs_review`를 기록했다. 이 블록의 분류·분할·연결에는 Solar, GPT, 외부 LLM, 임베딩, vector DB를 사용하지 않았다.

### 검색 승인 경계 수정

기존 importer는 `pending_review`로 registry에 저장할 문서를 먼저 retrieval table에 넣는 순서였고, corpus 재구성 SQL도 `review_status != 'rejected'` 조건을 사용했다. 따라서 명시적으로 반려되지 않은 pending 문서가 검색될 수 있었다.

다음과 같이 수정했다.

- importer가 registry에 `pending_review` version을 먼저 기록한다.
- retrieval table 재구성은 current version이면서 상태가 정확히 `approved_for_search`인 문서만 읽는다.
- `Review-TermsDocument.ps1`로 `approved_for_search`, `rejected_license`, `rejected_privacy`, `rejected_quality`, `deprecated`를 기록한다.
- reviewer와 reason을 필수로 받고 `terms_review_events`에 event ID, 대상 version, 결정, 사유, UTC 시각을 남긴다.
- 결정 후 seed fixture와 승인 current version만 사용해 FTS/search table을 다시 만든다.
- importer 입력의 `public_fixture_allowed`는 계속 무시하므로 검색 승인과 Git 공개 승격은 별도다.

단위 테스트는 pending 문서가 `terms_document_versions`에는 존재하지만 `terms_documents`와 FTS에는 없고, 명시 승인 후에만 나타나며, 개인정보 반려 문서는 계속 검색되지 않는 것을 확인한다.

### 검증과 다음 경계

추가한 검증:

- 24개 source role coverage와 모순 검사
- 한국어 조항 번호와 `제2조의2` 분할
- section offset 연속성과 원문 재조립
- 조 번호 없는 fallback과 중복 조 번호 flag
- exact/fuzzy annotation 연결과 불일치 queue
- pending 차단, 승인 반영, 반려 차단, audit event 저장

다음 작업은 대량 자동 승인이 아니다. 먼저 공정위 정상/이상 문서와 AI Hub exact/fuzzy/unmatched 표본을 나누어 사람이 확인하고, license·privacy 상태를 구조화한 뒤 작은 국내 1차 corpus만 승인한다. 그 corpus와 겹치지 않는 질의-근거 gold set을 만들어 FTS5 `Recall@5`, MRR, 출처 일치율을 측정한 후에만 RAG 확장을 판단한다.

## 2026-07-15 공개 약관 사람 검토 패킷

### 목적

224,727개 section을 사람이 전부 읽는 대신, 자동 처리의 정상·경계·실패 유형을 빠짐없이 볼 수 있는 작은 1차 검토표를 만들었다. 이 단계에서도 AI 의미 판단과 검색 승인은 수행하지 않았다.

### 구현

- `review_packet.py`에 source/stratum별 SHA-256 최저 순위 표본 추출기를 추가했다.
- 난수와 실행 시각을 사용하지 않아 같은 입력이면 같은 item과 hash가 생성된다.
- AI Hub annotation은 exact, fuzzy high/mid/boundary, unmatched low/short/ambiguous로 분리했다.
- 문서 구조는 중복·역순·조 번호 없음, section 품질은 short/long/large preamble/suspicious Unicode로 분리했다.
- annotation 검토 item은 정규화 원문에서 annotation index와 target index를 다시 찾아 target text를 붙였다.
- 미연결 annotation은 최고 후보 section index를 review queue에 기록해 비교 발췌를 제공한다.
- section 원문은 최대 3,000자만 패킷에 넣고, 긴 본문은 앞·뒤 발췌 사이에 생략 표시를 넣었다.
- CSV는 Excel의 한글 인식을 위해 UTF-8 BOM으로 생성하고, reviewer와 모든 결정 열은 빈 값으로 둔다.

재생성 명령:

```powershell
.\scripts\Process-PublicCorpus.ps1
.\scripts\New-PublicCorpusReviewPacket.ps1
```

조항 결과 재생성은 24.28초, 검토 패킷 생성은 6.44초가 걸렸다. 기본 최대 8건 설정에서 AI Hub 114건, 공정위 29건, 총 143건이 생성됐다. annotation 비교 item은 54건이다.

전수 구조 검사는 다음을 확인했다.

- item 143개와 고유 ID 143개
- annotation target 누락 0건
- 비교 section 누락 0건
- 미리 채워진 review 결정 0건
- 최대 발췌 길이 2,999자
- 동일 입력 재실행 전후 `review-items.jsonl` SHA-256 일치

출력은 `.artifacts/review-packets/public-corpus-v1`에 있으며 `review-checklist.csv`, `review-items.jsonl`, `summary.json`, `README.md`로 구성된다. 사용 방법과 허용 상태는 `docs/PUBLIC_CORPUS_REVIEW.md`에 정리했다.

### 남은 사람 판단

패킷은 검토 비용을 줄였지만 다음 결정을 대신하지 않는다. reviewer가 license, privacy, parse quality, annotation quality, final decision, reason을 작성해야 한다. 작성 결과를 바로 검색 DB에 넣지 않고 먼저 허용값·필수 사유·source별 일관성을 검증한 뒤, 선택된 section만 version/hash provenance와 함께 registry에 적재하는 importer를 구현해야 한다.

## 2026-07-15 검토 결과 Validator와 Pending Importer

검토표 작성 이후의 수동 실수를 차단하고 검색 승인 경계를 유지하기 위해 validator와 importer를 구현했다.

### Validator

`Validate-PublicCorpusReview.ps1`은 CSV의 143개 item ID가 JSONL 기준본과 정확히 일치하는지 확인한다. source, stratum, document ID는 변경할 수 없고, 완전히 빈 검토 행만 pending으로 허용한다. 일부 열만 작성했거나 허용값 밖의 상태, 10자 미만 사유, annotation 유무와 맞지 않는 `annotation_quality`는 거부한다.

출처 검토는 별도 `source-review.json`에 기록한다. local search 허용은 `research_only` 또는 `redistributable` 상태, reviewer, reason, timezone 포함 시각, 하나 이상의 HTTP(S) 근거 URL이 있어야 한다. 행의 license 상태와 출처 상태가 다르거나 privacy가 `clear`가 아니거나 parse가 `pass`가 아니면 `candidate_for_search`를 허용하지 않는다.

검증 출력은 `.artifacts/review-results/public-corpus-v1/validated-results.jsonl`과 `summary.json`이다. review 값과 source 결정을 hash로 보존하며 검색 상태를 변경하지 않는다.

### Pending Importer

`Import-ReviewedPublicCorpus.ps1`은 기본 dry-run이다. 검증 결과의 eligible section을 `.artifacts/processed-corpus` 원문과 ID/SHA-256으로 다시 대조하고, 같은 원문 문서의 section을 하나의 `TermsDocument` version으로 묶는다.

importer는 validator 출력을 신뢰 전제로 두지 않는다. 결과 JSONL이 수정된 경우에도 review hash, candidate 결정, privacy/parse gate, source 이용 조건, 행/source license 일치, section/source content hash를 독립적으로 재검사한다.

`-Apply`를 명시하면 다음만 수행한다.

- `terms_sources`와 `terms_document_versions`에 `pending_review` current version 저장
- 실제 section 원문과 provenance를 document JSON에 보존
- `terms_public_review_import_runs`에 결과 파일 hash와 실행 건수 기록
- `terms_public_review_item_links`에 version, review item, section, review hash, source review 연결
- FTS 재구성 시 pending version이 제외되는지 유지

단위 테스트는 dry-run에서 DB가 생성되지 않는 것, apply 후 합성 검색 문서 3개가 그대로인 것, pending version과 audit link가 생성되는 것, 별도 `approved_for_search` 결정 후에만 검색 문서가 4개가 되는 것을 확인한다. 재적용은 동일 version을 duplicate로 처리한다.

실제 빈 패킷으로 세 명령을 연속 실행한 결과는 review item 143, pending 143, validated 0, eligible 0, pending document 0이었다. 실제 `.artifacts/terms-corpus.sqlite`에는 적용하지 않았다.

## 2026-07-27 AndroidControl 기반 범용 Navigation 정확도 보강

Rico·MobileViews 도입은 취소하고 AndroidControl의 목적·단계·행동 시연만 공개 사전 근거로 사용하도록 결정했다. 휴대폰 연결 없이 노트북에서 다음을 구현하고 검증했다.

- TensorFlow·android_env 없이 공식 20개 GZIP TFRecord를 읽는 경량 streaming converter
- 스크린샷과 실제 입력 문자열을 제외한 정규화 JSONL 계약
- 목적·단계 지시·대상 UI 문구를 검색하는 SQLite FTS5 인덱스
- 한국어 목적과 영문 AndroidControl 시연을 연결하는 기능 동의어
- 목적을 계정 진입, 결제/멤버십 관리, 해지 등 중간 기능으로 분해하는 계획
- 버튼 위치·부모·주변 문맥을 이용한 기능 분류
- K-EXAONE 프롬프트에 최대 5개 유사 시연과 독립 후보 점수 제공
- 낮은 모델 확신, 낮은 독립 점수, 작은 후보 점수 차이에 대한 안내 거절
- 홈 하단 콘텐츠 `구독`과 Premium 결제 구독 관리의 동음이의 회귀 테스트
- 이메일·전화번호와 입력 문자열을 인덱스에서 제거하는 개인정보 경계

공식 split 메타데이터와 첫 shard의 256MB range만 로컬에 내려받았고 약 50GB 전체 원본은 다운로드하지 않았다. 실제 50개 에피소드의 280개 행동을 추가 의존성 없이 변환해 공식 wire format 호환성을 확인했다. 합성 정규화 fixture 10건과 실제 280건으로 로컬 인덱스 290건을 생성했다. 전체 노트북 검사에서는 API, 모바일 TypeScript, Android 설정, 공개 배포, OpenAPI, 문서, PowerShell, 웹 데모 검사가 모두 통과했다. 합성 Navigation Top-1은 9/10이며 나머지 1건은 잘못된 후보를 선택하지 않고 계정·개인정보 후보가 모호하다고 거절했다.

실제 K-EXAONE 회귀 호출에서도 유튜브 홈의 콘텐츠 `구독` 탭을 선택하지 않고 독립 기능 판단이 `내 페이지`를 0.78 확신도로 안내했다. 현재 제공 endpoint가 일부 호출에서 Hermes arguments 뒤에 비정상적인 중괄호를 반복해 유효한 JSON을 만들지 못하는 현상이 있어 이 실행은 안전 폴백으로 완료됐다. 모델이 독립 판단과 같은 후보를 반환하면서 confidence만 0으로 보내는 경우에도 강한 독립 점수를 유지하는 회귀 검사를 추가했다. 따라서 모델 출력 형식이 불안정해도 동음이의 오안내로 전환하지 않는다.

## 2026-07-28 탐색 대기·자동 종료·배민클럽 보강

앱 본체의 `탐색 시작`과 실제 화면 자동 탐색을 분리했다. 첫 동작은 `해당 어플을 열고, 시작을 눌러주세요` 안내 말풍선과 원형 `▶` 버튼만 표시하며, 사용자가 대상 앱을 연 뒤 `▶`를 눌러야 탐색 활성 플래그와 새 세션 nonce가 생성된다. 이후 아이콘은 고정 중심 12-spoke 로더로 바뀐다.

최종 목적 기능이 있는 화면을 찾으면 서버가 `phase=destination_reached`, `status=goal_completed`, `automation.action=stop`을 반환한다. APK는 목적 버튼을 누르지 않은 채 탐색 활성 상태를 지우고 플로팅 서비스를 자동 종료한다. 화면에 안전 후보가 없을 때는 접근성 노드 스크롤을 우선 실행하고 실패 시 실제 스와이프 제스처로 대체하며, 같은 화면 탐색 범위를 2회에서 4회로 늘렸다.

배달의민족 구독 해지를 위해 기능 사전을 v1.3.2로 갱신하고 `마이배민`, `배민클럽 이용 중`, `마이배민클럽`, `배민클럽 이용정보`, `해지하기`, `자동결제 해지`, `정기결제 해지`를 범용 계정·구독 관리·구독 상세·해지 기능에 연결했다. 실기기에서 현재 경로가 `마이배민 → 배민클럽 이용 중 → 마이배민클럽 화면 아래쪽의 해지하기`임을 확인했다. WebView가 화면 밖 요소를 접근성 트리에 미리 노출하더라도 실제 화면 영역 안에 들어온 요소만 분석하며, `해지하기`가 보이면 자동 클릭하지 않고 종료한다. 탐색 실패 응답도 플로팅 서비스를 완전히 종료하여 새 탐색이 반복 실행되지 않도록 했다.

## 2026-07-28 최종 목적지 우선 기능 그래프 탐색

현재 화면에서 다음 버튼을 반복 추측하던 구조를 최종 기능 우선 구조로 확장했다. 검토 가능한 JSON 원본과 SQLite 런타임 인덱스로 구성된 교차 앱 기능 사전을 만들었으며, v1.1 사전은 기능 85개, 한국어·영어 별칭 773개, 긍정·부정 문맥 566개, 목적 33개, 의미 경로 edge 79개를 포함한다. 계정·결제·구독·개인정보뿐 아니라 언어·화면·접근성·재생·다운로드·저장공간, 로그인 기기·세션, 연결 계정, 주문·주소, 콘텐츠 기록·보관함, 추적·개인화·차단 사용자, 법적 문서·앱 정보까지 확장했다. `구독`처럼 앱 문맥에 따라 의미가 바뀌는 라벨은 화면 위치와 주변 메뉴의 긍정·부정 근거를 별도로 계산한다.

미지 앱 탐색 세션에는 55초, 자동 메뉴 16회, 깊이 9의 기본 제한을 적용했다. 기능 사전에서 `safe_navigation`으로 분류되고 현재 노드가 low risk, 비체크형, 비입력형인 경우에만 자동 클릭한다. 안전 후보 간 점수 차이가 작으면 K-EXAONE Hermes 판단을 안전 후보 allowlist 안에서만 tie-breaker로 사용하며, 모델 장애나 불확실성이 남으면 자동 탐색을 중단한다. 최종 기능 후보는 경로의 마지막 수동 단계로 저장할 뿐 클릭하지 않는다.

목적 화면을 찾으면 DFS 경로를 `universal_routes`에 저장하고 자동 뒤로가기로 시작 화면까지 복귀한다. 서버 응답이 `guiding`으로 전환되는 순간 APK도 로컬 `guide` 모드를 영구 저장한다. 이후 중간 메뉴와 최종 버튼은 모두 사용자가 직접 누른다. 자동 클릭 실패는 `failed` 전이와 exploration attempt로 남아 동일 분기를 다시 누르지 않는다.

노트북 시뮬레이션에서는 `My page → Payments and subscriptions → Premium membership`을 탐색하고 `Cancel subscription`을 최종 후보로 확정한 뒤 세 단계 뒤로가기로 시작 화면에 복귀했다. 새 세션은 저장 경로를 즉시 재사용하면서 `automation.action=none`을 유지했다. 기능 사전, 최종 기능 금지, 탐색 예산, 경로 재사용, API 응답 계약을 포함한 전체 API 단위 검사는 통과했고 기존 범용 Navigation 기준선은 9/10을 유지했다. 모바일 TypeScript, Expo prebuild, Android 설정 검사는 통과했다. 이 노트북에는 Android SDK가 없어 Gradle의 Android class resolution 단계만 실행하지 못했으며, 생성된 Java 소스는 별도 javac 구문 검사에서 syntax error가 없음을 확인했다.
## 2026-07-28 교차 앱 공통 메뉴 관문 v1.4

앱별 저장 경로가 없는 제주항공 회원가입 사례를 기준으로 기능 사전을 v1.4.0으로 확장했다. 기존 사전에는 회원가입 최종 기능은 있었지만 경로가 `환영 화면 → 회원가입`으로만 구성되어 `마이페이지 → 로그인/회원가입 → 회원가입` 같은 일반적인 중간 관문을 자동 탐색할 수 없었다.

`navigation.menu`, `account.entry`, 신규 `auth.entry`, 신규 `auth.login.entry`를 회원가입 목적의 공통 관문으로 추가했다. 계정 허브를 사용하는 모든 목적에는 `전체메뉴`, 설정 허브를 사용하는 모든 목적에도 `전체메뉴`를 낮은 가중치의 안전 후보로 자동 확장한다. 규칙은 JSON의 `gateway_rules`에 저장하고 적재 시 SQLite 목적 경로와 기능 edge로 물질화하므로 런타임에는 빠른 인덱스 조회만 수행한다.

`로그인/회원가입` 결합 버튼은 회원가입 최종 목적지로 오인하지 않고 안전한 중간 관문으로 탐색한다. 반대로 아이디·비밀번호 입력 요소가 보이는 로그인 폼에서는 `로그인`을 제출 버튼으로 간주해 자동 클릭 후보에서 제거한다. 앱별 경로가 전혀 없는 합성 제주항공 화면에서 `마이페이지 → 로그인/회원가입`을 자동 탐색하고 순수 `회원가입`에서 자동 종료하는 회귀 검사를 추가했다.
## 2026-07-28 교차 앱 메뉴 DB 품질 평가 v1.4.1

공통 메뉴 DB의 양이 아니라 실제 탐색 품질을 지속적으로 측정하기 위해 `cross-app-menu-benchmark.v1.json`을 추가했다. 회원가입, 구독 해지, 계정 삭제, 마케팅 알림, 언어 변경, 환불, 개인 데이터 삭제, 주문 취소, 고객센터, 배송지 관리의 서로 다른 화면 단계 33개를 앱 경로가 없는 독립 패키지로 평가한다. 각 사례는 목표, 화면 제목, 경쟁 버튼, 기대 버튼, 자동 탐색 또는 최종 정지 동작을 명시한다.

첫 실행에서 발견한 `전체메뉴` 구독 관문 누락, 자연어 환불 목적 인식 실패, `개인정보`를 `개인정보 삭제`로 보는 과잉 종료를 수정했다. 삭제·환불·주문 취소 목적은 명시적인 삭제·환불·취소 문구가 있어야 최종 목적지로 인정한다. 설정, 결제·구독, 구매 내역, 활성 서비스, 알림, 마케팅 수신, 데이터, 고객지원, 언어·지역, 주문·배송의 실제 UI 변형 별칭도 추가했다.

v1.4.1 런타임 사전은 기능 107개, 별칭 1,037개, 문맥 근거 727개, 목적 47개, 기능 연결 163개다. 새 교차 앱 평가 33/33과 기존 범용 탐색 기준선 9/10을 함께 통과했으며 공개 API에 기존 HTTPS 주소를 유지한 채 배포했다.

## 2026-07-30 Navigation 온톨로지 v8 및 독립 되먹임 확장

휴대폰 없이 검증 가능한 기능 의미 DB를 97개 영역, 1,192개 기능, 1,068개 목적으로 확장했다. v7에는 데이팅·전자도서관·뷰티예약·보육·전자서명·크리에이터·가상자산·스포츠팀을, v8에는 자격증명 보관·회계·CRM·고객상담·POS/재고·현장공사·기사배차·장애 온콜을 추가했다. canonical 카탈로그는 별칭 16,527개, 주변 문맥 24,049개, 목적 패턴 20,108개, 조합 규칙 43,105개, 공식 1차 출처 235개를 포함한다.

독립 평가는 총 1,429개 사례·4,903단계로 1,068개 목적과 1,192개 기능을 100% 참조한다. v7 독립 팩은 120개 사례·480단계, v8 독립 팩은 한·영 각각 138개씩 총 276개 사례·1,104단계다. 두 팩은 `tuning_allowed=false`로 봉인했고 위험 버튼을 정답 클릭으로 둔 사례는 0개다. 별칭 충돌 전용 개발 벤치는 배차 업무의 모호한 `픽업` 문맥을 역할 한정 표현으로 고친 뒤 939개 중 939개를 실제 런타임 경로로 해결했으며 독립 정확도와 분리해 기록한다.

별칭 문맥 보정은 파생 문맥의 함수·필드·값을 장부로 기록한 뒤 다음 생성 전에 그 값만 제거하도록 바꿨다. 따라서 사람이 작성한 문맥을 보존하면서 materializer를 반복 실행해도 최종 v8 SHA-256 `1a8edf4434b734d7033414d7fb2a0ee56e392427e96ec35a76b22749c090417f`가 동일하다. 414만 개 별칭 쌍에 대한 최적화·기존 판정 비교에서도 불일치 0건을 확인했다. 이번 단계는 노트북 fixture 기반 검증이며 실제 Android 단말 정확도 주장은 하지 않는다.

## 2026-07-30 Navigation 온톨로지 v9 및 독립 교차 도메인 평가

코드 저장소·커뮤니티 모임·후원·공용 EV 충전·식단·번역·운전자 규정·숙박 호스트·사업장 출입·농업 운영의 10개 영역을 추가했다. canonical v9은 107개 영역, 1,386개 기능, 1,252개 목적이며 별칭 19,671개, 주변 문맥 28,874개, 목적 패턴 24,524개, 조합 규칙 49,729개, 경로 단계 2,750개를 포함한다. 공식 출처는 260개이고 880개 기능이 출처와 직접 연결된다. 품질 하한도 이 실제 규모에 맞춰 단조 증가시켰으며 전체 107개 영역을 필수로 고정했다.

별도 작성한 `independent-cross-domain-v9.json`은 184개 신규 목적을 한국어·영어로 각각 한 번씩 평가한 368개 사례·1,472단계다. 신규 허브 10개와 terminal 184개를 포함한 기능 194개를 모두 참조한다. 결과를 바꾸는 최종 단계 338개는 전부 `stop` 또는 `no_click`이며 위험 요소의 정답 클릭은 0개다. 기존 팩까지 합친 독립 커버리지는 1,797개 사례·6,375단계로 v9의 1,252개 목적과 1,386개 기능을 100% 참조한다.

materializer를 정식 canonical에서 두 번 실행한 결과 두 파일의 SHA-256은 모두 `ee4573efb85a449ca7548cd4dc8ba615a468b10151bc3b8dff48f4ff10a63055`로 동일했다. 품질 점수 100, v9 독립 팩 봉인 검사, 전체 독립 커버리지 검사를 통과했다. 이 결과는 휴대폰 없이 수행한 데이터·시뮬레이션 검증이며 실제 앱 UI 정확도 주장은 별도 실기기 평가가 필요하다.

## 2026-07-30 Navigation 온톨로지 v10 운영·전문 분야 확장

임대관리·창고풀필먼트·설비정비·제조품질·연구실·교사업무·법률실무·식당운영·가족돌봄·가정에너지·가계도·조달의 12개 영역을 추가했다. canonical v10은 119개 영역, 1,616개 기능, 1,470개 목적이며 별칭 23,399개, 모순 제거 후 주변 문맥 34,535개, 목적 패턴 29,756개, 조합 규칙 57,577개, 경로 단계 3,186개를 포함한다. 역할 단서 9,225개, 상태 단서 33,776개, 위험 단서 13,054개를 갖추고 공식 1차 출처 292개 중 32개가 v10에서 추가되었다. 출처와 직접 연결된 기능은 1,110개다.

별도 작성한 `independent-operational-v10.json`은 218개 목적·218개 사례·872단계로 신규 기능 230개를 모두 참조한다. 12개 UI 표면, 13개 화면 상태, 4개 전환 유형을 포함하고 복구 단서와 역할 반전 단서를 각각 654개, 동음이의 방해 선택지를 218개 제공한다. 위험 요소의 정답 클릭은 0개이며 모든 최종 행동은 사용자에게 남긴다. 전체 독립 커버리지는 15개 팩, 2,015개 사례·7,247단계로 v10의 1,470개 목적과 1,616개 기능을 100% 참조한다.

별칭 충돌 보정기가 기능 자신의 정확한 별칭을 부정 문맥으로 추가할 수 있던 결함을 전역 불변식으로 차단했다. 자기부정 문맥 5개를 제거한 뒤 `Assignment`와 `Submit assignment` 같은 최종·중간 기능 충돌에서도 정확한 UI 라벨을 우선한다. materializer를 정식 canonical에서 두 번 실행한 결과 두 파일의 SHA-256은 모두 `0126fbad5817b7237a6d9342b2b4b5b530a3cbc40525e5d5b7a600e4f092ccce`로 동일했다. 품질 점수 100, v10 봉인 검사, 전체 독립 커버리지, 기능 카탈로그, 34,610개 문맥 구문 인덱스의 brute-force 동등성 검사를 통과했다. 이 결과는 휴대폰 없이 수행한 데이터·시뮬레이션 검증이며 실제 앱 UI 정확도 주장은 별도 실기기 평가가 필요하다.

## 2026-07-30 Navigation 온톨로지 v11 중요 운영 영역 확장

임상진료팀·약국조제·보험손해사정·항공승무·통신현장·ITSM/CMDB·보안관제·사회복지 사례관리·상속재산 관리·항만물류·임상시험 사이트·재난대응의 12개 영역을 추가했다. canonical v11은 131개 영역, 1,858개 기능, 1,700개 목적이며 별칭 27,935개, 주변 문맥 40,713개, 목적 패턴 35,892개, 조합 규칙 65,857개, 경로 단계 3,646개를 포함한다. 역할 단서 10,907개, 상태 단서 41,376개, 위험 단서 15,566개를 갖추고 공식 1차 출처는 342개, 출처와 직접 연결된 기능은 1,352개다.

별도 작성한 `independent-critical-ops-v11.json`은 230개 목적·230개 사례·920단계로 신규 기능 242개를 모두 참조한다. 한국어 115개와 영어 115개, 16개 UI 표면, 17개 화면 상태, 4개 전환 유형을 포함한다. 복구 단서 1,840개, 잘못된 역할·기록 단서 1,380개, 동음이의 방해 선택지 230개를 제공하며 위험 요소의 정답 클릭은 0개다. 전체 독립 커버리지는 16개 팩, 2,245개 사례·8,167단계로 v11의 1,700개 목적과 1,858개 기능을 100% 참조한다.

목적 문장이 기존 패턴과 정확히 맞지 않는 경우를 위해 희소 IDF 기반 의미 폴백을 추가했다. 폴백은 충분한 어휘 증거와 후보 간 점수 차이가 있을 때만 동작하고, 부정 표현·모호한 문장·기존 고신뢰 판정에는 개입하지 않는다. 개발용 한·영 우회 표현 60개에서 안전하게 승인된 11개는 모두 정확했고, 34개 기존 판정은 그대로 보존했으며, 근거가 약한 15개는 추측하지 않고 보류했다. 독립 평가 문장과 정답은 학습·튜닝 입력에서 계속 격리한다. 이 결과는 휴대폰 없이 수행한 데이터·시뮬레이션 검증이며 실제 앱 UI 정확도 주장은 별도 실기기 평가가 필요하다.

## 2026-07-30 Navigation 온톨로지 v12 전문 현장·행정 영역 확장

수의진료·치과진료·재가 방문진료·항공정비·철도운영·화물통관·전력망 현장·환경폐기물·광산안전·선거행정·연구과제행정·교정 사례관리의 12개 영역을 추가했다. canonical v12는 143개 영역, 2,110개 기능, 1,940개 목적이며 별칭 34,166개, 주변 문맥 51,840개, 목적 패턴 43,572개, 조합 규칙 73,537개, 경로 단계 4,126개를 포함한다. 역할 단서 14,234개, 상태 단서 56,466개, 위험 단서 19,862개를 갖추고 공식 1차 출처는 416개, 출처와 직접 연결된 기능은 1,604개다.

V12 원본은 기능별 의미 검사 1,440개, 충돌 검사 384개, 복구 검사 960개, 세대 격리 검사 720개를 포함한다. 신규 terminal 240개는 전부 `never_auto + before_action + user_owned_final_press`이며 결과를 바꾸는 162개 목적은 모두 high risk로 고정했다. 임시 canonical에서 materializer를 두 번 실행한 결과 두 파일의 SHA-256은 모두 `d519e4c5611842bbc8b8450c7884187bfe07da57d85a846353812b7ebf31d203`으로 동일했고, 품질 점수 100·findings 0·패턴 충돌 0을 확인했다.

별도 작성한 `independent-specialized-ops-v12.json`은 240개 목적·240개 사례·960단계로 신규 기능 252개를 모두 참조한다. 한국어 120개와 영어 120개, 20개 UI 표면, 23개 상태, 8개 전환 유형을 포함하고 복구 단서 2,160개, 잘못된 역할·기록 단서 1,680개, 동음이의 방해 선택지 480개를 제공한다. 위험 요소의 정답 클릭은 0개이며 전체 독립 커버리지는 17개 팩, 2,485개 사례·9,127단계로 v12의 1,940개 목적과 2,110개 기능을 100% 참조한다. 독립 세트의 봉인 해시는 `88fc2a75c95ee584290bce735c0a830be7bf179fce21544acb655430855acd2a`다. 이 결과는 휴대폰 없이 수행한 데이터·시뮬레이션 검증이며 실제 앱 UI 정확도 주장은 별도 실기기 평가가 필요하다.

고신뢰 오판과 느린 장문 fuzzy 비교를 보완하기 위한 bounded 문자·단어 TF-IDF 후보 검색기도 별도 서비스로 구현했다. v12 기준 1,970개 후보, 137,750개 feature, 332,401개 posting을 가지며 후보별 feature 176개·posting 길이 64개·캐시 512개를 넘지 않는다. 정상 cold build 10.07초, warm p95 1.9ms, 추정 인덱스 65.4MB, 계측 peak 약 129MB였다. 개발 우회 문장 60개 중 top-1은 16개였고 엄격한 채택 gate를 통과한 4개는 모두 정답이었다. 부정문은 후보를 보여줄 수 있어도 항상 `admitted=false`다. 현재는 관측·후보 비교용이며 production resolver와 독립 평가에는 연결하지 않았다.

## 2026-07-30 Navigation 온톨로지 v13 규제·고신뢰 시스템 확장

혈액은행·장기이식 조정·방사선치료·법원서기 사건행정·IP 출원 도켓·식품시설 검사·건축허가/코드집행·상하수도 플랜트·원전운영·파이프라인 무결성·박물관 컬렉션·항공교통관제의 12개 영역을 추가했다. canonical v13은 155개 영역, 2,362개 기능, 2,180개 목적이며 별칭 40,442개, 주변 문맥 65,794개, 목적 패턴 51,252개, 조합 규칙 81,217개, 경로 단계 4,606개를 포함한다. 역할 단서 17,687개, 상태 단서 74,919개, 위험 단서 24,614개를 갖추고 공식 1차 출처는 488개, 출처와 직접 연결된 기능은 1,856개다.

V13 원본은 의미 검사 1,440개, 교차 도메인 충돌군 61개·충돌 검사 732개, 복구 검사 960개, 세대 격리 검사 720개를 포함한다. 신규 terminal 240개는 전부 `never_auto + before_action + user_owned_final_press`이며 결과를 바꾸는 156개 목적은 모두 high risk다. 실제 canonical을 연속 두 번 materialize한 파일 SHA-256은 모두 `0f4a774e58a3a637d1be42a129345cc47763627c4dff9c1ff6ec3b839f26d65f`로 같아 byte-idempotence를 확인했고, 품질 점수 100·findings 0을 확인했다.

별도 작성한 `independent-regulated-systems-v13.json`은 240개 목적·240개 사례·960단계로 신규 기능 252개를 모두 참조한다. 한국어와 영어는 각각 120개, 20개 UI 표면, 24개 상태, 8개 전환 유형을 포함한다. 복구 단서 2,160개, 잘못된 역할·기록 단서 1,680개, 동음이의 방해 선택지 480개를 제공하고 위험 요소의 정답 클릭은 0개다. 전체 독립 커버리지는 18개 팩, 2,725개 사례·10,087단계로 v13의 2,180개 목적과 2,362개 기능을 100% 참조한다. 이 결과는 휴대폰 없이 수행한 데이터·시뮬레이션 검증이며 실제 앱 UI 정확도 주장은 별도 실기기 평가가 필요하다.

bounded 문자·단어 검색기는 관측 단계를 마치고 production resolver의 마지막 generic fallback으로 연결했다. 기존 reviewed/fuzzy/semantic concrete 판정은 char 검색을 호출하지도 않으며, generic 결과에서만 엄격한 score·margin·evidence·부정문 gate를 통과한 catalog intent/terminal을 채택한다. 통합 개발 사례는 5/5, 기존 의미 폴백은 11/11이었고 fingerprint별 lazy singleton build 1회, retriever cache 512개 상한, route/terminal override/avoid/safety 정책 보존을 검증했다.

## 2026-07-30 Navigation 온톨로지 v14 기관·역할 기반 운영 확장

진단검사실·수술실·의료수익주기·주택담보대출·금융범죄준수·대학학사·인체연구감독·긴급통신배차·공중보건감시·발전소·토지등기·우편망의 12개 영역을 추가했다. canonical v14는 167개 영역, 2,614개 물리 기능, 2,420개 목적이며 별칭 46,061개, 주변 문맥 78,514개, 목적 패턴 58,452개, 조합 규칙 89,857개, 경로 단계 5,086개를 포함한다. 역할 단서 20,195개, 상태 단서 90,906개, 위험 단서 29,366개, 공식 1차 출처 536개, 출처와 직접 연결된 기능 2,108개를 갖췄다.

V14 원본에는 의미 검사 1,440개, 충돌 검사 720개, 복구 검사 960개, 세대 격리 검사 720개가 있다. 신규 terminal 240개는 84개 민감 조회와 156개 결과 변경 기능으로 분리되며 최종 활성화는 모두 사용자 소유 경계에 남긴다. 실제 canonical을 연속 두 번 materialize한 SHA-256은 모두 `b3a7b784daa96c61ac54f9f8f58d3b1d4326f844611e3364cfb67c470fa38538`로 같았다. 품질 점수 100, findings 0, 목적 패턴 충돌 0을 확인했다.

별도 작성한 `independent-institutional-systems-v14.json`은 한·영 긍정 480개, 이전 세대 충돌 240개, v14 내부 충돌 120개, 불충분한 위험 요청 기권 120개의 총 960개 사례다. 전체 독립 커버리지는 19개 팩, 3,685개 사례·11,047단계로 v14의 2,420개 목적과 2,614개 기능을 100% 참조한다. 봉인 해시는 `7717428ecb0e65ad63121113265a05cede4f2fb9cce94b094d0d78ac4f183226`다.

참조 커버리지와 판정 정확도를 구분하기 위해 독립 목적 문장을 실제 resolver로 평가했다. 기권 120개를 제외한 3,565개 중 979개가 정답으로 기준선은 27.46%였다. 최근 전문 영역의 장문·역할·상태 표현에서 일반화 공백이 크다는 뜻이므로, 독립 실패 문장은 튜닝에 사용하지 않고 집계값만 다음 개발 사이클의 우선순위로 사용한다. 카탈로그 파생 개발 세트와 일반 알고리즘 개선 뒤 동일 봉인 세트에서만 다시 측정한다.

기능 동등성 감사에서 진정한 동치 10개 쌍을 하드 삭제하지 않고 canonical ID 오버레이로 연결했다. 물리 기능 2,614개는 논리 기능 2,604개로, 물리 목적 2,420개는 논리 목적 2,410개로 정규화되며 과거 ID는 계속 입력으로 허용한다. DB Gym의 20개 물리/논리 ID 차이는 모두 이 10개 동치 클래스의 정확한 대표 ID로 일치했다. 오버레이 적용 후 충돌성 프로브는 835/939에서 931/939(99.15%)로 향상했고 긍정 문맥 98.26%, 부정 문맥 100%를 기록했다.

V14 성능 검사는 문자 인덱스 후보 2,450개·feature 153,791개·posting 405,239개에서 cold build 19.63초, warm p95 1.9ms, 추정 인덱스 77.1MB, peak 152.9MB였다. 목적 resolver는 합성 전수 비교보다 7.8배 빨랐고 실제 저신뢰 문장 136개를 4.06초(33.5 qps)에 처리했다. 의미 폴백 warm p95는 0.122초였다. 모두 휴대폰 없이 수행한 데이터·시뮬레이션 검증이며 실제 Android 앱 정확도는 별도 실기기 gold 평가가 필요하다.

## 2026-07-30 Navigation 온톨로지 v15 권한·규제 운영 확장

공항 에어사이드, 연방 기록 처분, DOJ FOIA 사건, 댐 안전, NLRB 대표 사건, 특수교육 행정, 연금 관리, 선거자금 준수, 수출통제 허가, 방송국 준수, 앱스토어 릴리스, 도메인 등록의 12개 영역을 추가했다. canonical v15는 179개 영역, 2,866개 물리 기능, 2,660개 물리 intent이며 별칭 53,016개, 주변 문맥 109,230개, 목적 패턴 67,092개, 조합 규칙 98,737개, 경로 단계 5,566개를 포함한다. 역할 단서 24,047개, 상태 단서 112,395개, 위험 단서 35,102개, 공식 1차 출처 667개, 출처와 연결된 기능 2,360개를 갖췄다.

V15 소스 팩은 12개 hub와 240개 terminal을 추가하며 84개 민감 조회와 156개 결과 변경 기능을 분리한다. 공식 출처 131개, 의미 검사 1,440개, 충돌 검사 720개, 복구 검사 960개, 역할·자산·상태 격리 검사 720개를 통과했다. 최종 제어는 전부 `never_auto`, `before_action`, 사용자 소유 press로 고정했다. materializer를 연속 실행한 canonical SHA-256은 모두 `e0eeef03195a48ec8172421926d08c30823bc678c72ea72082bb513dbec36e24`였고 품질 점수 100, findings 0, 목적 패턴 충돌 0을 확인했다.

구현과 분리해 작성한 `independent-authority-systems-v15.json`은 한·영 긍정 480개, 이전 세대 충돌 240개, v15 내부 충돌 120개, 불충분한 위험 요청 기권 120개의 총 960개 사례다. 봉인 해시는 `bc9d0cd2535ca40e6fefb74e5f295060696e2477f1af90246e96ebda5a9eeece`다. 어댑터는 840개 `stop`과 120개 `no_click`로 투영하고, 모든 사례에서 위험 클릭과 자동 최종 실행을 0으로 유지한다. 전체 독립 참조는 20개 팩, 4,645개 사례·12,007단계로 v15의 2,660개 intent와 2,866개 기능을 100% 참조한다.

독립 목적 판정은 기권을 제외한 4,405개 중 1,092개 정답(24.79%)이며 신규 v15 분할은 840개 중 125개(14.88%)였다. 이는 참조 커버리지와 자연어 resolver 정확도가 서로 다른 지표임을 다시 확인한 결과다. 봉인된 실패 문구는 신규 기능 튜닝에 사용하지 않고 집계값만 피드백으로 사용한다. 기존 역사 회귀에서 빠진 지도 길안내 한 건은 앱 독립적인 `경로 안내 + 명시적 시작` 의미 조합으로 복구했으며, 나머지 독립 결과는 유지됐다.

기능 동등성은 기존 10개 클래스·10개 alias를 유지한다. 물리 기능 2,866개와 intent 2,660개는 논리 기능 2,856개와 intent 2,650개로 정규화되며 고유 canonical default terminal은 2,648개다. v15의 신규 252개 기능은 모두 기존 동등성 클래스와 분리돼 있다.

V15 문자 검색기는 후보 2,690개, feature 163,017개, posting 441,679개에서 cold build 16.98초, warm p95 1.7ms, 추정 인덱스 83,235,833바이트, 관측 peak 173,574,994바이트를 기록했다. 개발 세트에서 허용된 후보 4개는 모두 정답이었다. 이 결과와 독립 목적 판정은 휴대폰 없이 수행한 데이터·시뮬레이션 검증이며 실제 Android UI·OCR·자동 탐색 정확도는 별도 실기기 gold 평가가 필요하다.

## 2026-07-30 전수 이중언어 목적 표현 개발 벤치

canonical v15의 2,660개 intent 전체를 한국어와 영어로 각각 한 번씩 재서술하는 5,320개 개발 사례를 추가했다. 역할·대상·상태·행동·도착 조건을 8개 문장 구조에 균등 분배했고, 정규화 길이 4 이상인 별칭·목적 패턴의 직접 복사와 부분 감싸기, 중복, 불투명 fallback은 모두 0개다. 1~3자 원문이 남은 사례 89개와 resolver `goal_rules` 어휘가 action에 남은 사례 4,366개는 숨기지 않고 결합도 진단으로 따로 기록하며 각각 현재 기준선보다 증가하지 못하게 한다. 이 세트는 `catalog_derived=true`, `tuning_allowed=true`, `independent_accuracy_evidence=false`로 고정해 봉인 독립 평가와 혼동하지 않는다.

현재 resolver 기준선은 정답 253개, 안전한 generic 1,300개, 오답 3,767개이며 카탈로그 정책 자체의 안전 위반은 0개다. 보호가 필요한 목적이 비보호 기능으로 잘못 해석된 845개는 실제 클릭 위반과 분리한 `expected_boundary_mismatch_cases`로 기록한다. 전수 실행은 약 102.46초, cold p95 28.6ms, warm p95 24.9ms였다. 정답 최저 250, generic 최대 1,400, 오답 최대 3,800과 경계 불일치 최대 845의 보수적인 회귀 gate를 두어 all-generic·all-wrong resolver나 안전 경계의 추가 악화가 구조 검사만 통과하지 못하게 했다. 이 결과는 기존 카탈로그 문구에 과적합된 탐색기가 역할·대상·상태를 풀어쓴 장문에서 아직 크게 부족하다는 개발 피드백이다. 생성 결정성, 모든 intent·언어·문장군의 정확한 분포, 카탈로그 SHA 고정, 금지 복사, 사용자 최종 클릭 경계, 처리량 검사를 `Test-ApiUnit.ps1`과 `Run-NavigationDatabaseFeedback.ps1`에 연결했다.

## 2026-07-30 Navigation 카탈로그 v16 격리 후보팩

공식 출처 검증과 16개 부분 근거 정제를 반영한 v16 후보를 canonical materializer와 분리된 모듈로 구현했다. 후보는 12개 신규 영역, 252개 기능(hub 12·terminal 240), intent 240개이며 민감 조회 84개와 결과 변경 156개를 모두 `never_auto` 사용자 최종 실행 경계로 분리한다. 정규화 고유 공식 URL 127개가 모든 terminal에 연결되고 고아 출처는 0개다. 별칭 7,010개, 목적 패턴 8,654개, 조합 규칙 8,880개를 포함한다.

격리 검증은 의미 1,440개, 교차 충돌 720개, 복구 960개, 역할·자산·상태 격리 720개, equivalence 보고 240개를 확인했고 미해결 충돌은 0개였다. 기존 v15 원본은 변경되지 않았으며, 비파괴 append-only 병합·재병합 idempotence·부분 삽입 및 출처/정의 변조 fail-closed를 통과했다. 격리 병합 해시는 `a090f0f1e04653518d351b276ec8f9819a2013cabd878a8d9bdbffc99e1e9103`이고 예상 canonical 규모는 191개 영역·3,118개 기능·2,900개 intent다. 이 단계는 승격 후보 검증이며 canonical v15를 대체하지 않는다.

후보 구현을 보지 않고 최종 ID·분류 표면만 공유받은 별도 작성자가 v16 봉인 독립 평가 960개를 구성했다. positive 한·영 각 240개, 이전 세대 충돌 240개, v16 내부 충돌 120개, 불충분한 거버넌스 기권 120개이며 240개 terminal은 positive에서 각각 정확히 두 번 참조된다. 전 사례가 `tuning_allowed=false`이고 위험 정답 클릭과 자동 최종 실행은 모두 0개다. screen/state/action 증거와 역할·자산·관할·복구 단서를 포함하며 대표 목표·production 문구의 exact/near-copy와 내부 ID·좌표·고정 경로 누출을 거부한다. 사례 payload 해시는 `7fddb3f8e20c5d434a589aaa087bf145eafc6c40a957ed9f2aa6f68a23a946cf`, canonical seal은 `eb28f54609f8739c4ac349e1849cbd6c2b13a857da085bf987a27aa2d70c56b7`이다.

## 2026-07-30 V16 격리 후보 평가 표준 검증 배선

`navigation_v16_isolated_evaluation_unit.py`를 `Test-ApiUnit.ps1`의 표준 단위검사 목록에 추가했다.
`Run-NavigationDatabaseFeedback.ps1`에는 계약 검사
`v16_isolated_evaluation_contract`와 집계 실행
`v16_isolated_candidate_evaluation`을 fixture adapter 단계 뒤에 연결했다. 집계 실행은
`Evaluate-NavigationV16Isolated.py`를 `--gate`로 호출하고 결과를
`.artifacts/navigation-feedback/v16-isolated-aggregate.json`에 기록한다.

평가기는 canonical V15를 읽기 전용 기준선으로 두고 V16 후보를 메모리·임시 디렉터리에서만
병합한다. 구조 계약은 V15 179개 영역·2,866개 기능·2,660개 intent, 격리 V16 191개
영역·3,118개 기능·2,900개 intent, 목적 fixture 840개, 상태형 fixture 960개를 고정한다.
정규화된 목적 fixture와 상태형 fixture seal은 각각
`55528db74b22bdf7b6ca355f17f121c96a4da8727bfd6a834462569e4f5cce37`,
`5ac5da1c6a190fb4673813106fd04e72823db21504fcc05a1c37fc0b9b799bb1`이다. 출력은 집계값만
허용하며 목적 문장, case ID, 실패 상세, confusion pair, DB 제안은 남기지 않는다.

이 배선은 V16의 정식 통합이 아니라 승격 검토를 위한 격리 후보 평가다. 다른 평가 작업의 실제
결과가 확정되기 전에는 정확도 수치나 하한을 새로 선언하지 않았고, 기본 정확도 하한 0에서
안전·격리 불변식만 gate한다. canonical V15 파일은 변경하지 않았다.

## 2026-07-30 V16 임시 materialization 회귀와 actual 재평가

canonical은 계속 V15로 유지한다. `navigation_catalog_v16_materialization_unit.py`로 canonical
catalog와 equivalence 파일의 임시 복사본만 V16 승격 경로에 통과시킨 회귀는 578.8초에 PASS했다.
임시 결과는 191개 영역, 3,118개 물리 기능, 2,900개 물리 intent였고 equivalence projection은
물리/논리 기능 3,118/3,108개, 물리/논리 intent 2,900/2,890개, 물리/논리 기본 terminal
2,898/2,888개, 동치 클래스 10개, alias 10개였다. 동일 복사본에 연속 두 번 적용했을 때 catalog와
equivalence가 각각 byte-for-byte 동일했다. 일부 V16만 삽입한 입력과 equivalence 정의를 변조한
입력은 쓰기 없이 fail-closed했으며, 검사 전후 canonical 두 파일은 byte 단위로 변하지 않았다.

이 약 9~10분짜리 승격 회귀는 `Run-NavigationDatabaseFeedback.ps1`의 `Mode=deep`에서만
`v16_materialization_candidate_contract` 단계로 실행되게 배선했다. `quick`과 `full`에는 해당
비용을 추가하지 않는다. 이 결과는 임시 복사본의 승격 회귀 PASS이지 canonical V16 통합이 아니다.

첫 V16 격리 actual은 stateful evaluator가 허용하는 500자 schema 경계를 넘은 입력에서 중단돼
aggregate 보고서를 생성하지 못했다. 봉인 원문을 잘라 goal 정확도 의미를 바꾸지 않도록 goal-only
평가는 원문을 그대로 보존하고, stateful consumer에 전달하는 복사본만 결정적으로 최대 500자로
projection하도록 수정했다. 이 수정의 unit은 117.6초에 PASS했다. actual 재평가는 현재 진행
중이므로 실제 정확도와 새 정확도 gate 하한은 아직 기록하지 않는다.
