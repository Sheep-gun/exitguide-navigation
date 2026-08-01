# Public APK Deployment

## User Experience

The public release APK does not require USB, ADB, a laptop API, or a shared Wi-Fi network. A user only needs:

1. the ExitGuide APK,
2. an internet connection,
3. Android overlay and AccessibilityService permissions enabled by the user.

The APK contains no K-EXAONE credential. It sends the sanitized current-screen structure to the public ExitGuide HTTPS backend, and the backend calls K-EXAONE with the protected server-side key.

The current sideloaded competition APK declares `QUERY_ALL_PACKAGES` only so the AccessibilityService can resolve the active target app's exact version and enforce app/version-scoped route reuse on Android 11+. It does not use that permission to upload an installed-app inventory. A future Play Store release must replace or justify this broad visibility through the store policy review, for example with a supported-app `<queries>` allowlist.

## Runtime Architecture

```text
ExitGuide APK
  -> GitHub runtime config (HTTPS, address rotation only)
  -> public Cloudflare HTTPS tunnel
  -> FastAPI on 127.0.0.1:8100 in the competition server
  -> K-EXAONE API
  -> recommendation returned to the floating card
```

`deploy/mobile-runtime.json` is intentionally published as a public GitHub Gist and contains only the public API URL and lifecycle metadata. It never contains an API key. The main source repository may remain private. The installed app checks the public Gist on startup, so a changed tunnel URL can be applied without rebuilding the APK. If the lookup is temporarily unavailable, the APK keeps using its saved or build-time fallback URL.

## Deploy Or Rotate The Backend

From the dedicated worktree, run:

```powershell
.\scripts\Deploy-PublicNavigationApi.ps1
```

During phone development, deploy uncommitted API work without changing Git history and keep the existing public URL with:

```powershell
.\scripts\Deploy-PublicNavigationApi.ps1 -IncludeWorkingTree -PreserveTunnel
```

`-IncludeWorkingTree` snapshots only `apps/api`, `contracts`, and `fixtures` through a temporary Git index; it does not stage or commit the developer's work. `-PreserveTunnel` restarts the API behind the existing healthy Cloudflare process, so installed APKs keep the same HTTPS address.

The script deliberately invokes `C:\Windows\System32\OpenSSH\ssh.exe` with `~/.ssh/exitguide-navigation-config`; it does not invoke the unrelated Windows `Ssh` shell item. It uploads only committed API/contract/fixture files plus the minimum EXAONE environment variables. Credentials are written to a mode-600 server file and are never placed in the APK or Git.

The server keeps two tmux sessions:

- `exitnav-public-api`: FastAPI bound to server loopback only.
- `exitnav-public-tunnel`: the public HTTPS tunnel.

The command prints `Public Navigation API is ready: https://...trycloudflare.com`. After a URL rotation:

1. update `deploy/mobile-runtime.json`,
2. set `apps/mobile/app.json` `extra.apiBaseUrl` to the same URL as the build fallback,
3. run `.\scripts\Publish-MobileRuntimeConfig.ps1` to update the anonymous public Gist,
4. commit and push the source/runtime record,
5. rebuild the APK only when a new fallback binary is desired.

Already installed APKs do not need to be rebuilt merely because the runtime file changed.

## Operations Check

```powershell
$ssh = "$env:WINDIR\System32\OpenSSH\ssh.exe"
$config = "$HOME\.ssh\exitguide-navigation-config"
& $ssh -F $config exitguide-gpu "tmux ls; cat /home/exitnav/workspace/universal-navigation-api/runtime/public-url.txt"
```

Then check the printed public URL from any internet connection:

```powershell
Invoke-RestMethod "https://<public-host>/health"
```

## Lifecycle Limit

The current competition GPU server allocation ends on 2026-08-14. This deployment therefore makes the APK independent of the developer laptop, but it is not a permanent commercial hosting contract. Before that date, move the FastAPI service to a persistent backend or extend the server allocation. The runtime-config mechanism lets the installed APK follow the replacement HTTPS address.
