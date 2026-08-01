# Navigation V16 blinded baseline

Status: **measured, not promoted**

Measured on 2026-07-30 with the aggregate-only isolated evaluator. The run
completed successfully as an evaluation process, but the quality gate is not
passed. V16 remains an in-memory candidate and the canonical V15 catalog was
not modified.

## Immutable evaluation inputs

- Canonical V15: 179 domains / 2,866 functions / 2,660 intents
- Isolated V16: 191 domains / 3,118 functions / 2,900 intents
- Goal cases: 840
- Stateful cases: 960, including 840 routable and 120 abstention-only cases
- Aggregate report SHA-256:
  `9cac9cb1a19dcb774b9e4d92c3871bcb9dda2a750dd6a94a27bd0d1c162b5bbd`
- Runtime catalog SHA-256:
  `f74ef8b2fd91ad858f3144ff418d07ac4e47f11343a541233fdeefff7db3fcc0`
- Canonical V15 SHA-256 before and after:
  `e0eeef03195a48ec8172421926d08c30823bc678c72ea72082bb513dbec36e24`
- Equivalence overlay SHA-256 before and after:
  `197aa0253c0353e439a6679a3597efed25297c44c554a15c0402a30f077ab2e8`
- Nine evaluator/runtime source hashes were identical before and after.

The aggregate contains no goal text, case identifier, detailed failure,
confusion, or suggestion. The sealed fixture and leftover interrupted-run
temporary files must not be inspected for tuning.

## Aggregate baseline

| Measurement | Result |
|---|---:|
| Exact independent goal resolution | 33 / 840 (3.9286%) |
| Generic fallback | 302 / 840 (35.9524%) |
| Routable stateful success | 306 / 840 (36.4286%) |
| Routable goal interpretation | 34 / 840 (4.0476%) |
| Abstention no-click accuracy | 93 / 120 (77.5%) |
| Combined stateful success | 399 / 960 (41.5625%) |
| Wrong-click rate | 55.8333% |
| Unsafe-click rate | 0% |
| Automated dangerous final presses | 0 / 960 |
| User-owned final presses | 960 / 960 |

The principal failure is generalization, not automated execution of a
dangerous final action. The catalog is conservative at the final-action
boundary but does not yet understand unfamiliar natural-language goals or
ambiguous state screens reliably enough for promotion.

## Promotion decision

V16 must not be materialized into the canonical catalog from this baseline.
The next revision may use only official source packs, catalog-authored
development matrices, public development fixtures, and newly written
non-sealed regression cases. It must not copy or inspect sealed phrases or
detailed sealed failures.

Required work before one blinded promotion rerun:

1. allow strong role/asset/state/jurisdiction semantic evidence to challenge a
   weak incidental reviewed-rule match while preserving exact reviewed goals;
2. strengthen generic, wrong-role, wrong-record, wrong-jurisdiction, loading,
   offline, error, and relogin no-click boundaries;
3. preserve zero unsafe final presses and user ownership of every final press;
4. pass legacy, collision, recovery, false-positive, performance, and
   materialization regressions on development data;
5. rerun the sealed aggregate once for the new architecture version, without
   consulting case-level data.
