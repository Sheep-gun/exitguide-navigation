# Navigation coverage gaps — v6 open-world ontology

Collected: 2026-07-30
Status: reviewed and materialized into the canonical runtime catalog; independent evaluation pending

## Purpose

The v5 base catalog had 797 functions, 697 intents, and 73 domains. Its
remaining open-world gap is not a lack of generic buttons such as **menu**,
**settings**, or **history**. It is the domain meaning that lets a navigation
agent distinguish, for example, a vehicle key from an account passkey, a toll
transaction from a parking receipt, a payroll bank account from a transfer,
or a pet prescription from a human prescription.

`scripts/navigation_catalog_v6_data.py` adds a semantic destination layer for
eight high-utility domains. It is intentionally independent of package names,
screen coordinates, recorded click paths, and any one provider's UI. The
module remains independently reviewable and is now wired into the catalog
materializer after v5.

## Delivered coverage

| Domain | Hub | Terminal functions | Representative destinations |
|---|---:|---:|---|
| `automotive_vehicle` | 1 | 12 | vehicle status, lock/unlock, remote start, climate, charging, phone key, driver access, service, roadside assistance |
| `parking_tolls` | 1 | 14 | parking sessions, extension, reservation, receipts, citations, toll balance, transponder, auto-replenishment, violations |
| `hr_payroll` | 1 | 16 | payslips, tax documents, direct deposit, withholding, timecard, leave, benefits, expenses, employment verification |
| `fitness_membership` | 1 | 15 | activity history, goals, connected apps, class booking, check-in, pause/cancel, renewal, credits, waitlist |
| `home_services` | 1 | 14 | provider search, quote, booking, property access, chat, reschedule/cancel, invoice, tip, protection claim |
| `civic_local` | 1 | 14 | local services, problem report, evidence, status, nearby requests, sanitation, bulky pickup, permits, inspections, records |
| `pet_care` | 1 | 14 | pet profile, vaccinations, vet care, prescriptions, grooming, training, boarding, microchip, recovery, lost-pet report |
| `grocery_loyalty` | 1 | 14 | shopping list, aisle location, weekly offers, coupons, loyalty card, rewards, fuel points, pickup, substitutions, receipts |

Total v6 layer:

- **121 functions**: 8 hubs and 113 terminal destinations;
- **113 one-to-one intents**;
- **2,194 bilingual aliases**;
- **2,938 bilingual goal patterns**;
- **4,450 semantic goal rules**, including 1,742 compositional rules;
- at least 10 terminal destinations in every domain.

The canonical materialization now produces 918 functions, 810 intents, and 81
domains. Two consecutive full materializer runs produced an identical raw
SHA-256; the feedback report records the hash for each run.

## App-agnostic representation

Every destination carries:

- Korean and English aliases;
- positive context and explicit negative context;
- role hints for text, buttons, tabs, rows, switches, cards, and icon-adjacent labels;
- state cues for enabled, selected, active, pending, completed, or unavailable states;
- risk cues and a declared terminal policy;
- a two-step semantic route: domain hub to final destination;
- first-party evidence references.

The intent layer combines domain-qualified aliases, request framing, and
reordered semantic atoms. This supports unfamiliar wording without pretending
that a provider-specific screen path is universal. Negative cues suppress
nearby but wrong concepts such as ride hailing versus vehicle control, transit
fare versus tolls, human healthcare versus pet care, and food delivery versus
grocery pickup.

No v6 function or intent stores Android package names, resource IDs, element
bounds, coordinates, screenshots, or app-specific route steps. Successful
screen exploration can later map observed nodes onto these destinations, but
such observations are a separate runtime graph and are not embedded here.

## Duplicate prevention

The layer does not duplicate generic concepts already owned by v1-v5,
including subscriptions, payment methods, refunds, appointments, order
tracking, addresses, medication reminders, smart-home controls, and generic
government filing. These decisions are recorded in
`EXCLUDED_AS_ALREADY_COVERED`.

Validation rejects:

1. function or intent ID collisions with v1-v5;
2. normalized goal-pattern collisions;
3. semantic goal-rule signatures owned by more than one intent;
4. any partial v6 materialization;
5. drift in a materialized function, intent, evidence registry, version, or
   description.

Set-derived metadata is persisted only after sorting and deduplication. Two
independent trial merges and an idempotent second merge produce byte-identical
canonical JSON.

## Evidence policy

All **62 evidence records** are first-party pages opened through the web
reader on the collection date. Each record stores publisher, title, HTTPS URL,
collection date, `official_primary` evidence level, successful verification
status, and verification method. Every v6 function cites one or more related
records, and the registry contains no orphan source.

The evidence set includes official support or product documentation from:

- Tesla, ParkMobile, E-ZPass New York, and the New York State Thruway
  Authority;
- ADP and Workday;
- Google Fit and ClassPass;
- Taskrabbit;
- NYC311 and the NYC Department of Buildings;
- Petco, PetSmart, AKC Reunite, and Chewy;
- Kroger, Walmart, and Target.

Provider names appear only in the evidence registry. Runtime aliases, routes,
and goal semantics remain provider-neutral.

## Safety boundary

The v6 draft contains 76 state-changing functions and 92 high-risk functions.
For every function in either category:

- `automation_policy` is `never_auto`;
- `stop_policy` is `before_action`;
- the matching intent requires user confirmation;
- the route stops before the consequential action;
- risk cues explicitly state in Korean and English that the user owns the
  final click.

This applies to vehicle controls, payments, payroll changes, bookings and
cancellations, civic submissions, claims, permissions, prescriptions,
microchip or contact changes, reward redemption, and order changes. The
ontology can guide the user to the destination, but cannot silently confirm
the action.

## Verification

`apps/api/tests/navigation_catalog_v6_data_unit.py` performs an offline trial
merge and verifies:

1. exact counts and one-to-one terminal/intent coverage;
2. all eight domains and at least ten terminals per domain;
3. source allow-list, collection metadata, official-primary evidence, and no
   orphan records;
4. bilingual alias/context/state/risk completeness;
5. safe final-action boundaries;
6. zero v1-v5 ID, normalized pattern, or semantic rule collisions;
7. schema-valid non-mutating merge;
8. runtime smoke resolution for every v6 terminal in both locales;
9. quality score 100 with zero goal-pattern collisions;
10. byte determinism, idempotence, and fail-closed drift detection.

Verified commands:

```powershell
.\apps\api\.venv\Scripts\python.exe scripts\navigation_catalog_v6_data.py
.\apps\api\.venv\Scripts\python.exe apps\api\tests\navigation_catalog_v6_data_unit.py
```

Latest result: **quality 100**, 113/113 terminals resolved in both Korean and
English smoke inputs, deterministic merge, and all fail-closed checks passed.

## What this does not prove

This layer proves ontology integrity, source traceability, deterministic
materialization, safety boundaries, and collision-free trial integration. It
does **not** prove first-seen-app navigation accuracy, icon recognition,
scroll/exploration efficiency, or success on an untouched device. Those claims
require a separately authored frozen evaluation set and later real-device
tests. No independent or sealed expected labels were opened while building or
testing this layer.

The remaining gate is external evaluation: a separate author is freezing
unseen Korean/English goals and app states so destination recall and
unsafe-action rate can be measured without using the ontology's own wording.
Until that fixture and later real-device gold pass, materialization must not be
misreported as first-seen-app accuracy.
