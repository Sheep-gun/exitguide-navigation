# TVING Public-Prior A/B Evaluation — 2026-08-04

## Scope

- app: TVING
- package: `net.cj.cjhv.gs.tving`
- version: `26.31.02` (`versionCode=20263102`)
- goal: `membership.join`
- safe destination: membership/pass/plan selection screen
- terminal boundary: stop before subscription confirmation, payment, credentials,
  personal-data submission, or final terms acceptance

## Preflight evidence

- Samsung SM-S936N connected and unlocked.
- TVING was first installed at `2026-08-04 04:05:10`.
- ExitGuide Executor APK is installed.
- ExitGuide AccessibilityService appears in the enabled setting and in the
  bound-service record from `dumpsys accessibility`.
- `stay_on_while_plugged_in=2`; no coordinate keep-alive is used.
- The APK was not reinstalled for this evaluation, so the install script was
  not run unnecessarily. If a later APK replacement occurs,
  `scripts/Install-NavigationExecutor.ps1` must restore and verify the actual
  service binding before exploration resumes.

## Leakage audit

All authoritative navigation-memory sources returned zero TVING records:

| Source | Result |
|---|---:|
| Decision verified cases | 0 |
| Decision screen observations | 0 |
| Runtime sessions | 0 |
| Human Gold / tracked app knowledge | 0 |
| Canonical App Knowledge generation | 0 |
| Public service transitions by package or TVING text | 0 |
| Public failure transitions by package or TVING text | 0 |
| Public task knowledge TVING text | 0 |

The preserved legacy repository contains `tving` only in a generic brand-word
catalog and a test phrase. The redesigned runtime does not import or execute that
legacy explorer, Gold replay, AndroidControl DB, or app-specific route.

## Isolation design

- A: public prior OFF, port 8110, isolated Runtime DB under `.../tving/a/`.
- B: public prior ON, port 8111, isolated Runtime DB under `.../tving/b/`.
- Both validation services use the dedicated
  `/srv/exitguide/runtime/navigation-api-validation-code` symlink. They never
  replace the production 8100 code symlink or its immutable split manifest.
- Both use the same read-only Decision DB, Solar/VLM configuration, app split,
  safety policy, and code commit.
- The production 8100 Runtime and Decision DB are not evaluation write targets.
- TVING validation observations are never promoted into canonical App Knowledge
  or Decision DB.

## Pending gate

Both isolated services must report `ready=true`, A must report public prior
disabled, and B must report planner-advisory public prior enabled. Only then may
the Executor collect candidate-complete TVING observations.
