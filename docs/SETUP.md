# Setup

## Current Machine Check

Detected initially before bootstrap:

- Java is installed.
- Codex bundled Node is available, but it does not include npm on PATH.

Not detected on PATH before bootstrap:

- Git
- npm
- npx
- adb
- Android SDK
- Android Studio

## Bootstrap First

Run the bootstrap script from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Bootstrap-Windows.ps1
```

The bootstrap script installs project-local Node.js and project-local MinGit under `.tools` when system tools are missing. Global PATH does not need to be changed.

## Install Soon

### Required For Mobile Development

- Python 3.12+
- Git for version control, if you prefer system Git over project-local MinGit

Expo SDK 54 requires Node.js 20.19.x or newer. The current project baseline uses project-local Node.js v24.15.0 under `.tools/node-v24.15.0-win-x64`.

Current project status: project-local MinGit is installed under `.tools/mingit-2.54.0` and is used by the Git helper scripts when `git.exe` is not on PATH.

### Required For Local Android Builds

- Android Studio
- Android SDK
- Android platform tools, including adb

This is needed for local emulator/device builds. If we use EAS cloud builds, local Android Studio can wait.

### Optional But Useful

- Expo Go on an Android phone for fast preview
- Expo account for EAS Build
- OCR/LLM API keys after the mock demo loop works

## Recommended Order

1. Run `.\scripts\Bootstrap-Windows.ps1`.
2. Continue API and mobile development with mock providers.
3. Add OCR/LLM keys.
4. Install system Git only if you want Git outside this project folder.
5. Install Android Studio only when local APK testing becomes necessary, or use EAS Build first.

## Current Dev URLs

- API local: `http://127.0.0.1:8010`
- Web demo: `http://127.0.0.1:8020`
- API LAN: run `.\scripts\Get-DevUrls.ps1`
- Expo Metro: `http://127.0.0.1:8081`

Use the LAN API URL inside the mobile app when testing from a physical phone on the same network.

Run `.\scripts\Get-DevUrls.ps1` from the project root to print the current phone URLs.
Run `.\scripts\Get-ProjectStatus.ps1` to print Git availability, latest generated artifacts, and recent work-block snapshots.
See `docs\GIT_WORKFLOW.md` for the difference between the GitHub plugin and local `git.exe`, plus the local branch helper.

## Local Checks

```powershell
.\scripts\Test-Api.ps1
.\scripts\Typecheck-Mobile.ps1
.\scripts\New-DemoReport.ps1
.\scripts\Export-OpenApi.ps1
.\scripts\Test-WebDemo.ps1
.\scripts\Test-Scripts.ps1
.\scripts\Test-CiWorkflow.ps1
.\scripts\Test-OpenApi.ps1
.\scripts\Test-DocsSync.ps1
.\scripts\Test-MobileFallbackCatalog.ps1
.\scripts\Test-TextHygiene.ps1
.\scripts\Test-ApiUnit.ps1
.\scripts\Test-AndroidConfig.ps1
.\scripts\Test-MobileAudit.ps1
.\scripts\Test-All.ps1
.\scripts\Test-All.ps1 -SkipMobileAudit
.\scripts\Get-ProjectStatus.ps1
.\scripts\New-DevBranch.ps1 -BranchName codex/demo-quality-structure
.\scripts\New-WorkBlockArchive.ps1 -Label demo-quality-structure
.\scripts\Build-AndroidPreview.ps1
```

Start both dev servers in the background:

```powershell
.\scripts\Start-DevServers.ps1
```

Start the desktop judge demo in the background:

```powershell
.\scripts\Start-JudgeDemo.ps1
```

## GitHub CI

The repository includes `.github/workflows/exitguide-checks.yml`. Once pushed to GitHub, it runs the Windows bootstrap script on push and pull request so API smoke tests, mobile typecheck, demo report generation, OpenAPI export/contract checks, web-demo checks, PowerShell syntax checks, text hygiene checks, and CI workflow validation run in CI.
