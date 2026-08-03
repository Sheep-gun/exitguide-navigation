# N100 Public Navigation Prior Integration Audit — 2026-08-04

## Outcome

The unpublished N100 integration at `b48af5a` was brought onto the current
promotion-pipeline v2 branch without replacing or bypassing the immutable App
Knowledge generation path.

Public evidence remains bounded planner context only:

- service transitions: at most 3 by the deployed configuration;
- failure transitions: at most 1;
- task knowledge: at most 1;
- runtime execution: forbidden;
- canonical promotion: forbidden;
- executable click targets: still limited to candidate IDs observed on the
  current screen;
- final safety enforcement: unchanged Python safe-action and risk gates.

The operating Decision DB and Runtime DB were audited read-only and were not
modified by this integration work.

## Task knowledge contract

`service-task-knowledge.v1.jsonl` was validated against the new Draft 2020-12
contract `navigation-task-knowledge.v1.schema.json`.

- valid rows: 570/570;
- unique task IDs: 570;
- `core_experience_eligible=false`: 570/570;
- role `goal_ontology_and_ambiguity_auxiliary`: 570/570;
- tier `task_knowledge`: 570/570.

The task records have no linked observed action outcome. They therefore cannot
be treated as Transition Outcome evidence or enter a canonical App Knowledge
generation without a separately observed and validated Interaction Episode.

## Retrieval defect found and fixed

The N100 implementation could accept an unrelated task when only its coarse
`service_categories` tag matched the requested domain. A real-estate browsing
task tagged `subscription_billing` was observed in a Korean membership-cancel
query. The task gate now requires the task goal text itself to contain a direct
domain-token match. Category-only matches are rejected.

This deliberately prefers returning no task hint over injecting a misleading
public task. Multilingual semantic retrieval can be added later only behind the
same frozen validation gate.

## Verification

All nine API unit-test files passed locally, including:

- public-prior read-only and bounded-context tests;
- category-only false-positive rejection;
- public task JSON Schema validation;
- public-prior OFF/ON A/B comparison gate;
- AndroidWorld research-policy integration;
- Runtime, Decision Memory, interaction adapter, experience profile, and
  promotion-pipeline v2 regression tests.

The production task JSONL also passed the contract validator with all 570 rows.

## Evaluation limitation and next gate

The Decision DB contains 88 verified cases, all from collection/train apps. The
Runtime DB contains no observations from either reserved validation app:

- `com.kbins.kbinsure` (KB Insurance);
- `ni.mh.android.launcher` (NH Nonghyup Property and Casualty Insurance).

Locked-holdout apps remain untouched. Consequently there are currently zero
valid frozen validation cases and no honest claim that the public prior improves
navigation accuracy can be made.

Next action: use the phone to record candidate-complete, isolated validation
cases from one reserved validation app, freeze them outside Decision DB, then run
the same cases through public prior OFF and ON. If B does not improve without an
accuracy or safety regression, do not expand or activate the public data path.
