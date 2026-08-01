# Navigation coverage expansion v7

v7 closes eight long-tail areas that were not represented as first-class,
app-agnostic destinations in v1-v6.  It adds 128 functions (8 hubs and 120
terminal destinations), 120 intents, 2,320 Korean/English aliases, 3,120 goal
patterns, and 4,696 compositional rules across 46 first-party sources.

| Domain | Terminal destinations | Representative goals |
| --- | ---: | --- |
| `dating_discovery` | 15 | discovery preferences, profile visibility, unmatch/block/report, identity verification, safety controls |
| `digital_library` | 15 | library cards, borrow/renew/return, holds, offline reading, content controls |
| `beauty_wellness_booking` | 15 | availability, booking, reschedule/cancel, waitlist, intake forms, deposits |
| `childcare_family_portal` | 15 | child feed, check-in/out, approved pickups, provider messages, billing, medication records |
| `esign_notary` | 15 | review/sign/decline, recipient routing, reminders, correction/cancel, audit report |
| `creator_monetization` | 15 | tiers, paid posts, member access, earnings, payout method/withdrawal, gifting |
| `crypto_assets` | 15 | buy/sell/swap, send/receive, recurring purchases, staking, allowlists, account lock |
| `sports_team` | 15 | schedules, availability, roster/lineup, team chat, fees, registration, livestream |

The runtime ontology contains no app package, resource ID, coordinate,
screenshot, or memorized application path.  Product help pages are evidence
for the existence and meaning of a destination only; brand names remain in the
source registry and are excluded from runtime semantics.

Every function carries bilingual aliases, positive and negative context,
role hints, state cues, risk cues, and source references.  Every terminal has
exactly one app-agnostic hub-to-destination intent.  All 78 state-changing and
95 high-risk destinations use `never_auto`; their routes stop before the final
action and explicitly reserve the final click for the user.

Validation is deliberately split:

- `navigation_catalog_v7_data_unit.py` proves schema validity, collision-free
  materialization, deterministic/idempotent merge, fail-closed drift handling,
  quality score 100, and bilingual runtime smoke resolution.
- `independent-long-tail-v7.json` is authored separately from aliases and goal
  rules.  It is frozen, not tuning-allowed, and measures coverage/generalization
  without feeding expected answers back into the ontology.
- Development probes may tune rules, but they must be marked catalog-derived
  and can never be reported as independent accuracy.

v7 is an expansion milestone, not a claim that all application categories are
finished.  The next independent audit is maintained in
`NAVIGATION_COVERAGE_GAPS_V8.md`.
