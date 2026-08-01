# Android Build

The fastest early testing path is Expo Go. The project is pinned to Expo SDK 54 for Play Store Expo Go compatibility. APK builds come later through EAS Build.

## Preview APK

From the repository root:

```powershell
.\scripts\Build-AndroidPreview.ps1
```

This requires an Expo account login.

The preview APK includes the ExitGuide Android overlay and AccessibilityService plugin. In the installed APK, grant both Android "display over other apps" and `ExitGuide Navigation` accessibility permissions. The service reads the active accessibility tree, posts it to `/v1/navigation/agent/observe`, and shows the recommended next menu in a floating card. It never clicks on behalf of the user.

## Local APK

If Android command-line tools are available through `ANDROID_HOME` or `%USERPROFILE%\ExitGuideAndroidSdk`, a local APK can be rebuilt with:

```powershell
.\scripts\Build-AndroidLocal.ps1
```

The script runs Expo prebuild, builds the requested Android variant for `arm64-v8a`, and copies the result to `.artifacts\apk\exitguide-ai-overlay-<variant>.apk`. Use a path without spaces for the Android SDK on Windows so the NDK invokes `clang++.exe` correctly.

The universal navigation architecture and device flow are documented in [UNIVERSAL_NAVIGATION_AGENT](UNIVERSAL_NAVIGATION_AGENT.md).

For a USB-connected development phone, keep the API URL at `http://127.0.0.1:8010` and run `adb reverse tcp:8010 tcp:8010`. The general-user release instead uses the public HTTPS backend configured in `app.json` and refreshes rotated addresses from the GitHub runtime configuration. No API credential is embedded in the APK. See [PUBLIC_APK_DEPLOYMENT](PUBLIC_APK_DEPLOYMENT.md).

Before starting an APK build, run the local checks from the repository root:

```powershell
.\scripts\Test-All.ps1
```

## Build Profiles

- `development`: internal development client
- `preview`: Android APK for judge/demo installation
- `production`: Android App Bundle

## API URL Note

During Expo Go testing, the app derives the API URL from the Expo host and uses port `8010`.

For a standalone APK, the checked-in build fallback and remote runtime configuration both point to the public HTTPS API. With USB attached for local development, `adb reverse tcp:8010 tcp:8010` maps the phone's `127.0.0.1:8010` to the PC API. The overlay uses the same saved API base URL as the main app.
