# ExitGuide Web Demo

Static browser demo for judge rehearsals. It calls the local FastAPI server directly for readiness checks, demo scenarios, prompt previews, flow checks, and synthetic upload calibration.

Run from the repository root:

```powershell
.\scripts\Start-JudgeDemo.ps1
```

Then open `http://127.0.0.1:8020`.

The integrated Navigation vertical slice is available at `http://127.0.0.1:8020/navigation.html`. It simulates AccessibilityService screen elements, requires the user to click each step, recovers from a route detour, and shows Terms evidence on the final cancellation screen.

The visual Dark Pattern MVP is available at `http://127.0.0.1:8020/dark-pattern.html`. It renders the synthetic app screen itself, highlights conflicting and safe choices, and lets users toggle paid add-ons or marketing consent to see the risk recalculate. The Navigation response embeds the same dark-pattern analysis.

For a start-test-stop rehearsal that verifies the live API and web page:

```powershell
.\scripts\Test-TestEnvironment.ps1
```

Validate the static page and JavaScript with:

```powershell
.\scripts\Test-WebDemo.ps1
```
