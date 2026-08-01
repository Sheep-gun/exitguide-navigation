# API Contract

## Health And Catalog

The local MVP API enables permissive CORS for development and browser-based demos.
Run `.\scripts\Export-OpenApi.ps1` to write the current machine-readable schema to `.artifacts\openapi.json`.

- `GET /health`: minimal liveness check.
- `GET /v1/status`: provider names plus `provider_ready` and `provider_notes`.
- `GET /v1/providers`: app-selectable provider options for server default, Google Gemini, OpenAI GPT, and EXAONE.
- `GET /v1/readiness`: demo-readiness checks for goals, scenarios, catalog integrity, manifest-backed fixtures, providers, and flow upload.
- `GET /v1/demo-quality`: reusable quality gate for readiness, scenario risk, flow risk-path, and synthetic-risk calibration.
- `GET /v1/goals`: goal IDs, display labels, and goal-first helper descriptions.
- `GET /v1/demo-scenarios`: deterministic demo scenario catalog.
- `GET /v1/demo-flows`: deterministic multi-screen flow catalog.
- `GET /v1/solar-demo-workflows`: saved Solar Pro 3 workflow outputs built from Korean Consumer Agency standard consultation cases.
- `GET /v1/synthetic-screens`: generated fixture metadata, expected risk, and recommended goal from `fixtures/synthetic-screens/manifest.json`.
- `GET /v1/consent-cases`: curated Korean consent/terms cases for backend calibration and future real-case collection.
- `GET /v1/consent-cases/quality`: quality gate comparing consent-case expected risks/directions against the current deterministic rule path.
- `GET /v1/terms-corpus`: seed Korean terms corpus for collection, retrieval, and local-rule experiments.
- `GET /v1/terms-corpus/search`: local lexical search over chunked terms sections.
- `GET /v1/terms-corpus/quality`: corpus coverage gate for document types, tags, and collection readiness.
- `GET /v1/collection-registry`: seed service, document-source, cancellation-flow, and review-task registry for collection workflow planning.
- `GET /v1/collection-registry/quality`: collection registry coverage gate for seed service/source/flow/review-task readiness.
- `GET /v1/navigation/routes`: route-graph catalog available to the Navigation runtime.
- `GET /v1/navigation/functions`: versioned cross-app function ontology, aliases, risk, and automation policy search.
- `GET /v1/navigation/agent/graph`: learned screen/action transition graph for one Android package.
- `GET /v1/navigation/agent/performance`: destination timing and safety metrics by measurement source.
- `POST /v1/navigation/agent/observe`: universal Navigation Agent observation, recommendation, and graph-learning endpoint.
- `POST /v1/navigation/agent/performance/complete`: Android display-side final TCD acknowledgement.
- `POST /v1/dark-pattern/inspect`: goal-aware dark-pattern inspection for a structured current screen.
- `POST /v1/prompt/demo`: preview the controlled JSON prompt for a deterministic demo scenario.

## Analysis

### `POST /v1/analyze`

Multipart upload:

- `goal_id`: optional; one of `/v1/goals` when the caller wants a fixed catalog goal.
- `goal_text`: optional free-form purpose text. When present, this becomes the analysis goal label.
- `infer_goal`: optional boolean. When `true` and `goal_text` is empty, the API infers the goal from the extracted screen.
- `provider_id`: optional; `server`, `google`, `gpt`, or `exaone`.
- `provider_api_key`, `provider_model`, `provider_base_url`: optional runtime provider settings sent by the mobile app.
- `screenshot`: image upload; defaults allow JPEG, PNG, and WebP up to `MAX_UPLOAD_BYTES`.

### `POST /v1/analyze/demo`

JSON body:

```json
{
  "provider_id": "google",
  "provider_api_key": "<redacted>",
  "provider_model": "gemini-3-flash-preview",
  "goal_text": "추가 결제 없이 가입하고 싶어요",
  "scenario_id": "checkout_addons"
}
```

Callers can still send `goal_id`, or send `{"infer_goal": true}` to let the API infer the goal from the demo screen.

### `POST /v1/analyze/flow`

JSON body:

```json
{
  "infer_goal": true,
  "scenario_ids": ["checkout_addons", "checkout_clean"]
}
```

`scenario_ids` must include 2-6 deterministic demo scenarios in the user's observed order.

### `POST /v1/analyze/flow/upload`

Multipart upload:

- `goal_id`, `goal_text`, `infer_goal`, and provider fields: same contract as `/v1/analyze`.
- `screenshots`: repeat this file field for 2-6 screenshots in the user's observed order.

The response is the same `FlowAnalysisResponse` shape as `/v1/analyze/flow`.

## Navigation

### `POST /v1/navigation/agent/observe`

Accepts the current Android AccessibilityService tree without requiring a prebuilt app route. In default `guide` mode the endpoint only returns manual guidance. User-started `explore` mode may return a device-executable click/back command for low-risk graph discovery. A newly discovered `shadow` route is never trusted automatically. An independently reviewed `verified_candidate` may be reused only for the same app/version/locale/target and only for visible, enabled, low-risk, non-checkable intermediate controls. The endpoint invalidates a mismatching candidate within at most two observations and falls back to generic exploration. Terminal or state-changing actions always remain user-owned.

Request fields:

- `request_id`, `session_id`, `app_package`, `app_version`, `locale`, free-form `goal_text`, and `operation_mode` (`guide` or `explore`)
- `screen.activity_name`, `screen.window_title`, `screen.event_type`, `screen.captured_at`, and `screen.elements[]`
- each element can include hierarchy, text/description, Android view ID, role, state, clickability, and bounds
- optional `transition` describing the preceding user or exploration click and its observed outcome; this teaches the graph an edge and records failed automation safely

Response fields:

- `screen_fingerprint`, normalized `goal_interpretation`, `phase`, and `decision_mode` (`exaone`, `graph_cache`, `route_cache`, `function_graph_exploration`, or `deterministic_fallback`)
- sanitized actionable `candidates[]` and one optional `recommendation`
- `recommendation.selected_element_id`, instruction, reason, expected next screen, confidence, risk, and user-confirmation requirement
- `automation.action`, `automation.safe_to_execute`, selected element, reason, and current time/action budget. APK execution requires all fields plus its own low-risk guard.
- optional `discovered_route` with the canonical target function, lifecycle, and ordered route steps; only reviewed `verified_candidate` or fully approved routes can drive guarded intermediate automation
- `graph_update` counts plus `transition_recorded`, and non-fatal `warnings[]`

The endpoint stores sanitized structure and transition metadata in local SQLite. Password nodes are excluded and likely email, phone, long-number, session, and token values are redacted before persistence.

### `GET /v1/navigation/agent/graph`

Requires an `app_package` query parameter and returns the accumulated screen/action/transition summary for that package: counts, screen fingerprints, activity/title metadata, visit counts, and learned transition success/failure counts.

### `GET /v1/navigation/functions`

Optional `query` and `limit` parameters search the SQLite-backed cross-app function ontology. The response includes catalog version and function/alias/context/intent/edge counts plus matching function IDs, names, descriptions, aliases, risk level, automation policy, terminal flag, and state-changing flag.

### `POST /v1/navigation/guide`

Accepts an Android package, a natural-language or canonical goal, session state, and the current AccessibilityService-style UI element list. The MVP runtime finds the current semantic route state, selects only a clickable element present in the request, and returns message-style guidance without clicking it.

Request fields:

- `request_id`, `app_package`, `app_version`, `platform`, and `locale`
- `goal_id` or `goal_text`
- `session.last_confirmed_state_id`, `session.failed_element_ids`, and `session.retry_count`
- `screen_elements[]` with `id`, visible text, accessibility description, role, clickability, and optional bounds

Response fields:

- `route_id`, `route_version`, `goal_id`, `current_step`, and `current_state_id`
- `target_element_id` and `target_label`; the ID is always one of the request elements or `null`
- `instruction`, `warning`, `confidence`, `navigation_state`, and `status`
- `requires_user_confirmation` for irreversible or recovery actions
- optional `recovery` and `terms_hint` data
- `dark_pattern`, the inspection result produced from the same current-screen element payload

The current vertical slice uses the synthetic `lab.exitguide.stream.demo` cancellation route. A mismatched screen returns a safe back request, two failed attempts return `needs_review`, and the final confirmation step includes evidence from the existing Terms corpus.

## Dark Pattern Inspection

### `POST /v1/dark-pattern/inspect`

Accepts a user goal, screen title/text, and interactive elements with visibility and choice metadata:

- `prominence`: visual emphasis from 1 to 3
- `default_selected`: whether a checkbox or option starts selected
- `optional`: whether the user can decline the item
- `monetary_impact`: whether the item changes the charge

The response returns `overall_risk`, `alignment_score`, `findings[]`, judged `elements[]`, `recommended_action`, and `proof_card`. The deterministic MVP reuses the existing goal-aware element judgment and risk rules, then adds explicit findings for retention misdirection, preselected paid add-ons, bundled consent, and asymmetric visual prominence.

## Canonical Analysis Response

Each analysis returns:

- `analysis_id`, a deterministic trace ID for the analyzed goal/screen/result shape
- `goal_id`, `goal_label`, `screen_title`, and `analysis_mode`
- `overall_risk`, `alignment_score`, and `risk_counts`
- `summary`
- `elements[]` with direction, risk, and reason
- `elements[].signals[]` with rule-engine cues such as default selection or monetary impact
- `recommended_action`
- `proof_card`

The response avoids legal conclusions and is safe to render directly in the mobile app.

## Demo Quality Response

`GET /v1/demo-quality` returns:

- `status`: `pass` only when readiness, scenario calibration, flow calibration, and synthetic calibration all pass
- `summary`: passed/total counts for readiness, scenarios, flows, and synthetic fixtures
- `checks[]`: the same readiness checks returned by `/v1/readiness`
- `scenario_calibrations[]`: expected vs. actual risk for deterministic scenarios
- `flow_calibrations[]`: expected vs. actual overall risk and ordered `risk_path` for deterministic flows
- `synthetic_calibrations[]`: expected vs. actual risk for generated synthetic fixtures

The demo report and web/mobile status surfaces use this endpoint so quality drift is caught consistently.

## Solar Demo Workflows

`GET /v1/solar-demo-workflows` returns saved Solar Pro 3 workflow outputs:

- `metadata`: source dataset, model provider/model id, prompt version, generation time, and not-legal-advice policy.
- `summary`: workflow count plus risk, confidence, and source dataset counts.
- `workflows[]`: case number, source reference, synthetic screen input, model risk/confidence, goal conflicts, reference guidance, recommended action, workflow steps, and evidence quotes.

These fixtures are sanitized demo outputs. They do not include API keys, authorization headers, raw model request payloads, or raw source archives.

## Universal Navigation Performance

`POST /v1/navigation/agent/observe` accepts optional `client_timing`:

- `measurement_source`: `real_device`, `real_device_gold`, `synthetic`, or `server_runtime`
- `exploration_elapsed_ms`: floating start-button tap to the current observation
- `screen_capture_ms`, `action_execution_ms`, `ui_settle_ms`, `external_wait_ms`

The response includes `performance` with the stage ordinal, the client timing fields, `server_total_ms`, `model_decision_ms`, `db_lookup_ms`, `screen_analysis_ms`, optional `time_to_confirmed_destination_ms`, route reuse, and current route rank. Subcomponent times are diagnostic slices of `server_total_ms` and must not be added to it again.

After displaying a `destination_reached` response, Android posts `session_id`, `measurement_source=real_device`, and the final display-side TCD to `POST /v1/navigation/agent/performance/complete`. This finalizes the authoritative device value including the last network/API round trip.

### `GET /v1/navigation/agent/performance`

Use `measurement_source=real_device` for the ordinary device baseline. The endpoint returns:

- destination accuracy and safe-stop rate
- unsafe and wrong click rates
- time-to-confirmed-destination p50/p90
- K-EXAONE decision p50/p90
- success within 10/30/60 seconds
- mean click/scroll/back counts and route reuse rate

### `POST /v1/navigation/agent/performance/complete`

Android sends the completed session ID and final display-side TCD after showing the destination indicator.

Synthetic desktop timings are explicitly tagged and are not a real-device baseline. The performance store never persists raw goal or screen text.

## Consent Case Dataset

`GET /v1/consent-cases` returns:

- `description`
- `metadata.dataset_schema_version`, `metadata.dataset_version`, `metadata.label_rubric_version`, and `metadata.rule_set_version`
- `summary.case_count`, `summary.element_count`, `summary.source_counts`, `summary.category_counts`, `summary.risk_counts`, and `summary.tag_counts`
- `cases[]` with `id`, `title`, `category`, `source_type`, `source`, `locale`, `recommended_goal_id`, `expected_risk`, `screen_title`, `screen_text`, `tags`, `data_notes`, and `elements[]`
- `source` with provenance and safety fields: `capture_method`, `artifact_type`, `redaction_status`, `review_status`, `public_fixture_allowed`, `contains_raw_screenshot`, `contains_ocr_text`, and `raw_artifact_in_repo`
- `elements[].expected_direction` and `elements[].expected_risk`, which make the dataset usable as a regression target

`GET /v1/consent-cases/quality` returns:

- `status`: `pass` only when dataset validation succeeds and every consent case matches expected overall risk, element risk, and element direction on the deterministic rule path
- `evaluation_scope`: currently `deterministic_rule_calibration`
- `not_evaluated`: quality layers that this endpoint deliberately does not measure, such as OCR extraction, live provider reasoning, mobile capture, or end-to-end runtime accuracy
- `limitations`: user-facing caveats explaining that this is not OCR/provider/end-to-end quality
- `metadata`: the same dataset metadata returned by `/v1/consent-cases`
- `summary`: the same dataset summary returned by `/v1/consent-cases`
- `calibration_summary`: total/pass/fail counts plus pass/fail breakdowns by risk and source
- `coverage`: warning-level dataset coverage targets for total cases, risk levels, false-positive guards, field candidates, prompt-injection resilience, and third-party sharing
- `calibrations[]` with expected and actual risk/direction maps for each case

The initial dataset is synthetic plus one generalized `field_candidate` shape. Labels follow `docs/LABELING_GUIDE.md`. Real captured cases must follow `docs/DATA_COLLECTION_POLICY.md`, must never commit raw screenshots or raw personal data, and should only be marked `captured_redacted` after redaction and approval.

## Terms Corpus

`GET /v1/terms-corpus` returns:

- `description`
- `metadata.dataset_schema_version`, `metadata.dataset_version`, and `metadata.collection_policy_version`
- `summary.document_count`, `summary.section_count`, `summary.chunk_count`, `summary.document_type_counts`, `summary.collection_method_counts`, and `summary.tag_counts`
- `documents[]` with source/provenance fields, tags, and section text

`GET /v1/terms-corpus/search` returns local lexical search results. Query parameters are `q=<query>` and optional `top_k=<n>`:

- `query`
- `total`
- `results[]` with `chunk`, `score`, and `matched_terms`
- `chunk.signals[]`, which are rule-friendly local signals such as `auto_renewal`, `cancellation`, `third_party_sharing`, `marketing_consent`, `location_ads`, or `withdrawal`

`GET /v1/terms-corpus/quality` returns:

- `status`: `pass` when current seed coverage targets are met
- `summary`: corpus counts
- `coverage_targets[]`: warning-level coverage targets for document types and important tags
- `warnings[]`

Run `.\scripts\Build-TermsCorpus.ps1` to build `.artifacts\terms-corpus.sqlite` from the fixture corpus. The SQLite database is a local artifact for retrieval and future RAG experiments; it is regenerated from fixture source. The generated artifact includes normalized document, section, chunk, signal, tag, and FTS5 chunk-search tables.

Run `.\scripts\Import-TermsCaptures.ps1 -InputPath <capture-json-or-folder>` to import OpenClaw/manual capture JSON into the same SQLite artifact. The importer accepts one JSON object, a JSON array, or an object with `captures[]`. Each capture should provide:

- `source_url`, `service_name`, `raw_text` or `html`
- optional `source_tool`, `collection_method`, `document_type`, `retrieved_at`, `tags`, and structured `sections[]`

Imported captures are staged in `.artifacts\terms-corpus.sqlite` tables `terms_ingestion_runs` and `terms_capture_staging`. Accepted imports are also written to source/version tables `terms_sources`, `terms_document_versions`, and `terms_review_events`; later imports rebuild the retrieval tables from the current accepted versions so previous accepted documents are not silently dropped.

Import rules are intentionally conservative:

- `retrieval_status` must resolve to `captured`; failed, partial, blocked, login-required, captcha, timeout, missing, or unknown statuses are rejected.
- `locale` must be `ko-KR`.
- URL query strings and fragments are stripped before storage.
- `public_fixture_allowed` in an imported capture is ignored; fixture promotion is a separate reviewed action.
- obvious private-data, secret, session, order/payment/customer ID, and Korean resident-registration-like patterns are rejected before persistence.

## Collection Registry

`GET /v1/collection-registry` returns:

- `description`
- `metadata.dataset_schema_version`, `metadata.dataset_version`, and `metadata.collection_policy_version`
- `summary.service_count`, `summary.document_source_count`, `summary.review_task_count`, `summary.flow_count`, `summary.flow_step_count`, and breakdown counts
- `services[]` with service aliases, country/language, platforms, priority, website/store URLs, and collection status
- `document_sources[]` with public source URL, source domain, locale, fetch state, content hash, active flag, robots flag, and manual-review flag
- `cancellation_flows[]` with user goal, platform, payment channel, verification method, confidence, current status, login/support flags, and expected step count
- `flow_steps[]` with ordered manual instructions, visible button/link text, expected result, and friction/risk notes
- `review_tasks[]` with entity references, priority, reason, status, reviewer note, and timestamps

`GET /v1/collection-registry/quality` returns:

- `status`: `pass` when the seed coverage targets are met
- `summary`: registry counts and breakdowns
- `coverage_targets[]`: warning-level targets for service inventory, public document-source inventory, manual flows, and review tasks
- `warnings[]`

Run `.\scripts\Build-CollectionRegistry.ps1` to build `.artifacts\collection-registry.sqlite` from `fixtures\collection-registry\registry.json`. The SQLite database is a local artifact for collection planning, operator review queues, and later OpenClaw/GLM worker handoff; it is regenerated from fixture source.

## Flow Response

Flow responses return:

- `flow_id`, a deterministic trace ID for the ordered flow result
- `goal_id`, `goal_label`, `overall_risk`, `alignment_score`, `screen_count`, and `highest_risk_screen_number`
- `risk_counts` aggregated across all screens
- `risk_path`, the ordered per-screen overall-risk sequence
- `summary`
- `screens[]`, where each item is a canonical analysis response
- a flow-level `proof_card`
