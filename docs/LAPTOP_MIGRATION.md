# Laptop Migration

Recommended development machine: the office laptop.

The project is light enough for a Ryzen 5825U and 16 GB RAM because the app uses Expo, the API is FastAPI, and OCR/LLM work is planned through external APIs. Use a physical Android phone with Expo Go instead of an Android emulator.

## What To Move

Move source files only.

Do move:

- `apps/`
- `docs/`
- `fixtures/`
- `scripts/`
- `.github/`
- `.editorconfig`
- `.env.example`
- `.gitattributes`
- `.gitignore`
- `README.md`

Do not move generated dependencies:

- `.tools/`
- `.logs/`
- `.artifacts/`
- `apps/api/.venv/`
- `apps/mobile/node_modules/`
- `__pycache__/`

The transfer archive created by `scripts/New-TransferArchive.ps1` follows this rule.

## On The Laptop

1. Extract `exitguide-source.zip`.
2. Open PowerShell in the extracted `exitguide` folder.
3. Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Bootstrap-Windows.ps1
```

4. Start servers:

```powershell
.\scripts\Start-Api.ps1
```

In another terminal:

```powershell
.\scripts\Start-Mobile-Interactive.ps1
```

5. Print laptop URLs:

```powershell
.\scripts\Get-DevUrls.ps1
```

6. Open the Expo URL in Expo Go.

The mobile app now auto-fills the API URL from the Expo host IP. If the laptop IP changes, restart Expo and check `Get-DevUrls.ps1`.

## Main PC Cleanup

Before leaving the main PC:

```powershell
.\scripts\Stop-DevServers.ps1
```

This stops ExitGuide API and Expo processes only.
