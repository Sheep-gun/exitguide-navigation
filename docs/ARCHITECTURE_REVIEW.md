# Architecture Review

## 2026-07-10 Data Plan Review

The mobile and API MVP are stable enough to serve as a validation surface. The main architecture risk has moved to the data plane: public source files have been collected, but normalization, review approval, retrieval evaluation, and analysis-time evidence are not yet one continuous path.

The most important findings are:

- `GET /v1/terms-corpus/search` currently searches the three public synthetic fixture documents, not the imported SQLite corpus.
- The importer stores source/version/review metadata, but current retrieval-table rebuilds can include `pending_review` documents because they exclude only rejected versions.
- The small JSON capture importer is not a bulk dataset parser. Its size, record-count, and `ko-KR` constraints require source-specific streaming adapters for the collected CSV, ZIP, PDF, HWP, and multilingual datasets.
- Current corpus and consent quality checks are deterministic seed/calibration gates. They do not measure retrieval accuracy, OCR quality, provider quality, or production-corpus safety.
- A lexical retrieval baseline and an independent question-to-evidence gold set should precede vector RAG or bulk LLM parsing.

The current target architecture is:

```text
collector or dataset adapter
  -> immutable raw artifact and manifest
  -> canonical staging record
  -> privacy/license/quality review event
  -> approved current document version
  -> lexical/vector retrieval index
  -> evidence-bound analysis response
```

The detailed implementation order and exit criteria live in `docs/ROADMAP.md`. The sections below preserve the earlier MVP review context.

## Current Judgment

The current architecture is appropriate for a contest MVP because it keeps the demo loop deterministic while preserving seams for real OCR and LLM providers.

The strongest parts are:

- Goal-first API contract shared by mobile, web demo, and report tooling.
- Provider boundaries for OCR and LLM, with explicit setup failures instead of silent fallback.
- Deterministic scenario, flow, and synthetic fixture catalogs.
- Rule-engine verification after model-style judgment.
- Local quality gates that now cover readiness, scenario risk, flow risk paths, synthetic calibration, rule-engine unit behavior, mobile dependency audit, Android config, OpenAPI contract, documentation sync, mobile fallback catalog sync, web-demo smoke, PowerShell syntax, and CI workflow shape.

## Improvements Made During This Review

- Added `/v1/demo-quality` so demo calibration is a reusable API surface instead of report-only logic.
- Added flow-level quality calibration for ordered `risk_path` checks.
- Tightened synthetic fixture readiness so manifest and PNG files must match both ways.
- Centralized API exception-to-HTTP translation in `app/http_errors.py`.
- Split FastAPI route registration into ops, catalog, and analysis routers.
- Surfaced quality status in mobile and web demo readiness UI.
- Added GitHub Actions scaffolding and local workflow validation.
- Added OpenAPI contract validation.
- Added work-block archives as a local branch-like safety fallback when Git is unavailable.
- Hardened demo/start/test scripts around working-directory state and port collisions.
- Reduced repeated mobile result-reset code in `HomeScreen`.
- Consolidated shared PowerShell helper logic for Git discovery, source archiving, and path safety into `scripts\ExitGuide.Common.psm1`.
- Added `scripts\Complete-WorkBlock.ps1` so quality gates, transfer archives, work-block snapshots, and status checks can be repeated as one safe branch-block routine.
- Reframed the mobile app around one integrated analysis intent instead of forcing users to pick from scattered narrow goals.
- Reworked the mobile first screen into compact connection state, integrated intent context, and Demo/Screenshot/Flow/History tabs.
- Added a neutral mock OCR fallback so passive community or comment screenshots do not inherit a cancellation fixture and become high risk.
- Added EXAONE-compatible OCR and LLM provider wiring behind the existing provider interfaces while preserving mock providers for deterministic gates.

## Mobile Redesign Reflection

The previous mobile surface exposed the system internals: API settings, provider state, goals, demo scenarios, flow demos, single upload, flow upload, and two histories all competed in one long scroll. That made the user choose the app's implementation model before they could ask the real question: "is this screen trying to pull me away from what I meant to do?"

The new structure keeps the implementation pieces but changes their hierarchy. The visible product concept is now one integrated intent card, then four task tabs. API state is compact unless setup needs attention. Results lead with the Proof Card because that is the most reusable artifact for a demo or judge review. The remaining risk details still exist, but they sit under the proof and action summary instead of defining the first impression.

The biggest remaining structural concern is that the app is still a single React screen with a lot of orchestration. It is acceptable for the MVP because the tabs are light and the quality gates protect the contracts, but the next real refactor should extract tab panels and analysis actions once a second screen or deeper navigation appears.

## Not Yet Worth Changing

- Splitting the static web demo into multiple files is not urgent. A single dependency-free `index.html` keeps judge setup simple.
- Replacing mock providers as the deterministic default is not necessary; real providers should be measured above the stable baseline.
- Moving from local SQLite to a managed database is premature until the normalized schema and review transitions stabilize.
- Adding a vector database is premature until FTS5 retrieval has a versioned evaluation baseline.
- Parsing every downloaded archive with an LLM is not justified before deterministic adapters handle the source formats and provenance.
- A larger mobile navigation refactor is not yet necessary because the app is still a single focused workflow.

## Next Structural Bets

1. Define the canonical staging/document/version/license schema and a streaming dataset-adapter interface.
2. Enforce `approved_for_search` as the only state eligible for retrieval and test the gate through SQLite and API paths.
3. Connect the API to the approved SQLite corpus and establish a versioned lexical retrieval baseline.
4. Route OpenClaw and manual capture through the same intake and review contract.
5. Add evidence citations to analysis responses before expanding mobile navigation or visual polish.
