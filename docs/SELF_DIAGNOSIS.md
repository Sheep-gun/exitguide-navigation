# Self Diagnosis

`scripts\Test-All.ps1` is the primary local quality gate. It currently checks:

- API smoke behavior, including provider failure paths, upload validation, demo quality, and flow responses.
- API rule-engine unit behavior for risk scoring, signals, and recommendations.
- Mobile TypeScript type safety.
- Mobile npm audit results for moderate-or-higher advisories.
- Android/Expo config, including asset paths, image dimensions, package name, SDK baseline, and EAS build profiles.
- Demo report generation and quality-gate pass/fail status.
- OpenAPI artifact generation and required path/schema constraints.
- Documentation route sync against the FastAPI OpenAPI surface.
- Provider configuration docs and missing-env readiness notes.
- Mobile fallback catalog sync against the API catalog.
- Mobile trace ID display in results, history, and Proof Card sharing.
- Mobile API URL normalization across input, saved settings, and request helpers.
- Mobile history dedupe by deterministic analysis and flow IDs.
- Mobile readiness detail display for failed setup checks.
- Mobile screenshot and flow media clear controls.
- Static web-demo checks and HTTP smoke loading.
- Live test environment startup, API HTTP checks, web loading, and tracked teardown.
- PowerShell script parse checks.
- Text hygiene for known mojibake/replacement-character failures.
- Project status output coverage for artifact, service, and Git block details.
- GitHub publish tooling shape, including portable `gh` bootstrap and non-interactive publish script coverage.
- GitHub Actions workflow shape.
- Expo doctor project checks.

For offline checks where the npm registry is unavailable:

```powershell
.\scripts\Test-All.ps1 -SkipMobileAudit
```

For faster CI/bootstrap runs where Expo doctor is intentionally skipped:

```powershell
.\scripts\Test-All.ps1 -SkipExpoDoctor
```

For faster bootstrap runs where live servers should not be started:

```powershell
.\scripts\Test-All.ps1 -SkipTestEnvironment
```

Before handing off a build or moving machines, run the full gate and then refresh the transfer archive:

```powershell
.\scripts\Test-All.ps1
.\scripts\New-TransferArchive.ps1
```

For one-command block completion, use:

```powershell
.\scripts\Complete-WorkBlock.ps1 -Label <label>
```

That wrapper runs the full quality gate, checks `git diff --check` when Git is available, refreshes `.artifacts\exitguide-source.zip`, writes a timestamped work-block snapshot, and prints project plus Git status.

## Mobile Restructure Reflection

- The mobile app now has one top-level purpose input instead of scattered goal selectors. Every screenshot, flow, and demo request uses either that purpose text or `infer_goal=true`.
- Tabs are now work surfaces rather than a long stacked page: screenshot first, flow second, history third, demo last.
- API status stays compact unless setup or provider readiness needs attention.
- The result area remains Proof Card first, with trace IDs and element cards below it for auditability.
- The Android overlay is intentionally APK-only. Expo Go stays useful for UI iteration, while the generated APK owns the `SYSTEM_ALERT_WINDOW` and media-projection capture path.
- Provider selection now lives in the phone UI. Requests can carry Google Gemini, OpenAI GPT, or EXAONE runtime settings; the local server default remains mock for repeatable checks.
- Remaining product risk: remote model calls require real credentials and provider billing or credits. The local default stays mock until the app sends runtime provider fields or `.env` opts into a remote provider.
