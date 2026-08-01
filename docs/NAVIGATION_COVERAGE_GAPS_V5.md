# Navigation coverage gaps — v5 independent draft

Collected: 2026-07-30
Status: independent ontology draft; not materialized into the runtime catalog

## Why this layer exists

The v4 catalog already covers 650 functions, 561 intents, and broad Android,
account, privacy, media, commerce, travel, insurance, work, and system
settings. The remaining practical gap is not another set of generic labels
such as **orders**, **settings**, or **history**. It is the service-specific
meaning around those labels: a restaurant waitlist is not a hospital waiting
list; a ticket transfer is not a bank transfer; and a parcel intercept is not
an order cancellation.

`scripts/navigation_catalog_v5_data.py` therefore adds only destinations that
cannot be represented faithfully by an existing v1-v4 function. It contains
no coordinates, screenshots, package names, or benchmark sentences.

## Prioritized gaps and delivered coverage

| Priority | Domain | Terminal functions | Why the existing catalog was insufficient |
|---:|---|---:|---|
| 1 | `food_ordering` | 11 | Item options, substitution, pickup/delivery, scheduled and group-order semantics were absent. |
| 1 | `restaurant_booking` | 11 | Reservation availability, waitlists, table alerts, seating choices, and restaurant messages are distinct from generic appointments. |
| 1 | `lodging_stays` | 13 | Stay search, amenities, check-in instructions, host contact, date changes, and cancellation refund preview need lodging context. |
| 1 | `event_ticketing` | 13 | Mobile entry, accessible seats, transfer/acceptance, resale, and venue updates have ticket-specific consequences. |
| 1 | `retail_banking` | 12 | Mobile check deposit, wires, debit controls, direct-deposit details, and transaction disputes were not covered by the existing transfer/loan/investment layer. |
| 1 | `government_digital` | 13 | Identity proofing, passports, immigration case tools, filing, fees, and office appointments need public-service context and strict safety boundaries. |
| 1 | `healthcare_provider` | 14 | Referrals, waiting lists, appointment notes, proxy access, care plans, questionnaires, and provider inboxes were missing from the generic health layer. |
| 1 | `parcel_courier` | 14 | Delivery holds, reroutes, windows, release, intercept, customs fees, and claims occur after store checkout and are not generic order tracking. |
| 2 | `ride_hailing_extended` | 11 | Pickup pin, accessibility preferences, multiple stops, business profiles, and wait-fee disputes extend the existing request/history concepts. |
| 2 | `workspace_administration` | 13 | Retention, exports/imports, guest/external access, channel lifecycle, shared-drive membership, and access requests require admin context. |
| 2 | `air_travel_planning` | 11 | Search-time fare, date, airport, bag-fee, price-tracking, emissions, and self-transfer semantics precede the existing booked-trip functions. |

Total: **136 terminal functions, 136 intents, 11 hubs, 68 official primary
sources, 2,353 bilingual aliases, 2,992 goal patterns, and 1,904 semantic goal
rules**.

## Duplicate prevention

The draft explicitly excludes concepts already owned by the current catalog:

- generic order tracking and cancellation;
- generic refunds;
- bank transaction history, card freeze, and recurring transfers;
- generic medical appointments and lab results;
- generic cloud link sharing and workspace member roles;
- flight check-in and boarding passes.

The code records each exclusion in `EXCLUDED_AS_ALREADY_COVERED`. Validation
also rejects any v5 function/intent ID collision and any normalized goal
pattern with more than one semantic owner across v1-v5.

## Evidence policy

Only first-party publisher pages were used. The registry stores publisher,
title, HTTPS URL, collection date, evidence level, and verification method.
Examples include DoorDash and OpenTable help, Airbnb Help, Google Travel Help,
Ticketmaster Help, Uber Help, Bank of America and Chase, Login.gov, the U.S.
Departments of State and Veterans Affairs, USCIS, the NHS, Slack, Google Drive
Help, and UPS.

Broad help indexes are used only where they genuinely enumerate a feature
family. Narrow features such as substitutions, scheduled delivery, ride PIN,
WAV, debit-card PIN and limits, identity proofing, passport applications,
government e-filing, proxy health access, nominated pharmacies, fit notes, and
organ-donation choices are linked to dedicated first-party pages.

Some official sites block generic scripted HTTP clients or apply regional
slugs. Those pages were verified through the web reader rather than treated as
missing. The source registry preserves the exact URL that was opened. Runtime
tests are deliberately offline and do not make the catalog build depend on a
publisher's transient availability.

## Safety policy

- Every state-changing function uses `automation_policy: never_auto`.
- Every high-risk or sensitive destination also uses `never_auto`.
- The route stops at `before_action`; the user owns the final click.
- Goal intents declare `user_confirmation_required` and
  `stop_before_action` for those functions.
- Financial transfers, purchases, cancellations, claims, government filings,
  medical submissions, access/retention changes, and delivery changes are
  never auto-confirmed.
- The draft contains no element coordinates and cannot silently execute an
  app-specific path.

Current draft counts: 82 state-changing functions and 89 high-risk functions;
all satisfy the boundary above.

## Verification and next gate

`apps/api/tests/navigation_catalog_v5_data_unit.py` proves:

1. exact counts and one-to-one terminal-intent coverage;
2. source allow-list, collection date, and official-primary evidence;
3. bilingual aliases plus positive, negative, state, and risk cues;
4. safe action boundaries;
5. no collision with the current materialized catalog;
6. schema validity after a non-mutating trial merge;
7. catalog quality score 100 with zero goal-pattern collisions;
8. idempotence and fail-closed behavior for partial or changed definitions.

This is still an ontology draft, not evidence of navigation accuracy. Before
runtime integration, a different author should create a frozen independent
fixture covering all 136 intents, including Korean/English paraphrases,
loading/error/re-login/permission states, icon-only menus, and dangerous
decoys. Only after an untouched baseline and safety evaluation should the v5
module be added to the materializer.
