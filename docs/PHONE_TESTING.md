# Phone Testing

## Public User APK (No USB)

The release APK is configured for the public ExitGuide HTTPS backend. A normal user installs the APK and uses mobile data or Wi-Fi; the laptop, USB cable, ADB reverse, and local API are not required. On first launch, the app uses the build-time public URL and also refreshes it from `deploy/mobile-runtime.json` through the configured GitHub HTTPS endpoint.

The user still has to enable Android overlay and `ExitGuide Navigation` accessibility permissions. These are Android consent requirements, not development connections.

See [PUBLIC_APK_DEPLOYMENT](PUBLIC_APK_DEPLOYMENT.md) for backend rotation and server lifecycle details.

## Standalone Universal Navigation APK

The AccessibilityService and floating overlay are custom native features, so test them with a release APK rather than Expo Go:

```powershell
.\scripts\Build-AndroidLocal.ps1 -Variant Release
adb install -r .\.artifacts\apk\exitguide-ai-overlay-release.apk
adb reverse tcp:8010 tcp:8010
```

The commands above describe USB development only. Keep the in-app API URL at `http://127.0.0.1:8010` only when deliberately testing the local API through ADB reverse. The public build uses the configured HTTPS backend.

The rest of this document describes the older Expo Go workflow for non-native screens.

## 1. Install On Phone

Install Expo Go on the Android phone.

## 2. Start Servers

From the project root:

```powershell
.\scripts\Start-Api.ps1
```

In another terminal:

```powershell
.\scripts\Start-Mobile-Interactive.ps1
```

If you do not need the QR screen and just want background servers, run:

```powershell
.\scripts\Start-DevServers.ps1
```

## 3. Get URLs

```powershell
.\scripts\Get-DevUrls.ps1
```

The IP can change after reconnecting the network, so use `Get-DevUrls.ps1` instead of relying on a remembered address.

## 4. Open App

Option A:

- Scan the QR code from the interactive Expo terminal with Expo Go.

Option B:

- Open Expo Go.
- Choose the option to enter a URL manually.
- Enter the Expo phone URL from `Get-DevUrls.ps1`.

## 5. In-App API URL

Inside the ExitGuide app, the API field is auto-filled from the Expo host IP and port `8010`. If it looks wrong, set it to the API phone URL from `Get-DevUrls.ps1`.

## 6. First Test Path

1. Open the app in Expo Go.
2. Confirm the API URL is the laptop or PC LAN URL from `Get-DevUrls.ps1`.
3. Tap one of the Phone demo cards.
4. Confirm Analysis and Proof Card appear.
5. Show the Prompt preview panel for the controlled JSON prompt.
6. Then try choosing a screenshot from the phone gallery.
7. Try Screenshot flow with 2-6 screenshots selected in order.

The demo cards do not need image files on the phone. They call `/v1/analyze/demo` directly.
The Flow demo cards call `/v1/analyze/flow`, while Screenshot flow calls `/v1/analyze/flow/upload`.

## Troubleshooting

If Expo Go says the project requires a newer Expo Go:

- The project SDK and Expo Go runtime are mismatched.
- This project is pinned to Expo SDK 54 for Play Store Expo Go compatibility.
- Run `.\scripts\Stop-DevServers.ps1`, then restart with `.\scripts\Start-Mobile-Interactive.ps1`.
- The mobile script clears Metro cache with `--clear`.

If the app says `Network request failed`:

- Make sure phone and PC are on the same network.
- Make sure the API URL uses the PC LAN IP, not `127.0.0.1`.
- Allow Python/Node through Windows Firewall for private networks if prompted.
- Check the API phone URL plus `/health` from the phone browser.

If Expo does not open:

- Run `.\scripts\Stop-DevServers.ps1`.
- Start API and mobile again.
- Check that port `8081` is not occupied by an old Expo process.

If the PC IP changed:

- Run `.\scripts\Get-DevUrls.ps1`.
- Update the API URL field in the app.
