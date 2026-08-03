# X negative/recovery memory deployment — 2026-08-04

## Scope

- Positive cases from the current app remain excluded from retrieval, preventing app-specific route replay.
- Only verified, observed same-app negative outcomes are reintroduced as safety memory.
- A same-screen, near-exact failed candidate match becomes a strong veto and never positive route support.
- Three repeated X `membership.cancel` wrong-destination outcomes and their `back` recovery rule were promoted.

## Offline result

| Metric | Live DB before (85) | Staged DB after (88) |
|---|---:|---:|
| Positive exact next action | 0.4853 | 0.4853 |
| Positive first action | 0.8182 | 0.8182 |
| Failed-click avoidance | 1.0000 (11/11) | 1.0000 (14/14) |
| Dangerous auto-clicks | 0 | 0 |

Evidence:

- `docs/evidence/navigation-offline-current85-negative-veto-20260804.json`
- `docs/evidence/navigation-offline-staged88-negative-veto-20260804.json`
- `docs/evidence/x-membership-cancel-recovery-staging-profile-validation-20260804.json`

## N100 deployment

- Decision DB: `/home/kyle/exitguide/runtime/navigation-decision-v2-0cd69a71.sqlite`
- Deployed DB SHA-256: `14c73a685ab7c915e9357ba6f99454e738f8f907d0b1abdf77c234825bb4478a`
- Retriever SHA-256: `213f1199cf5c551e0da2110d91328af18d49fe55e7fe592dc799283aff33830f`
- Previous DB backup: `/home/kyle/exitguide/runtime/navigation-decision-pre-x-recovery-20260804-0210.sqlite`
- Previous retriever backup: `navigation_decision_memory.py.pre-negative-safety-20260804`

## Live API smoke

- N100 status: `ready=true`, research models ready.
- Planner: Solar Pro 4 primary, Solar Pro 3 fallback.
- VLM: EXAONE 4.5 configured.
- Replayed the observed X failure screen through the live `/decide` endpoint.
- The prior failed candidate `a11y_a6e58a555cd6fc5bce56` was not selected.
- A different low-risk discovered candidate was returned by `semantic_intermediate_role_fast_path`.
- Smoke session was stopped and has no observed outcome, so it is not promotion-eligible.
- Service warning log entries after deployment: 0.
- Dangerous actions automatically executed: 0.

## Decision

The 88-case DB is deployed because it adds three real-device failure/recovery experiences, preserves positive accuracy, and raises avoidance of all evaluated failed clicks to 100%. Further device collection is paused for the requested intermediate review.
