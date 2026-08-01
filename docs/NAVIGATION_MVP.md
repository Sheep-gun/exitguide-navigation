# EGL Navigation MVP

This branch combines the Terms and dark-pattern backend in `exitguide` with the route contract designed in `exitguide-navigation`.

## What runs now

1. The browser simulator sends Android AccessibilityService-shaped elements to `POST /v1/navigation/guide`.
2. The backend infers `cancel_subscription` from the user's Korean goal text.
3. A semantic route graph matches the current screen using text anchors and button meaning rather than saved coordinates.
4. The response identifies only a clickable element that exists on the current screen.
5. The floating message tells the user what to press; the user performs every click.
6. A known later state is re-anchored, an unknown safe screen requests one back action, and two failed attempts stop with `needs_review`.
7. The final cancellation screen retrieves related evidence from the existing Terms corpus and shows it beside the navigation instruction.
8. The same screen elements are passed through the existing dark-pattern rules, and the Navigation response includes risk, findings, highlighted conflicting choices, and the safe target.

Standalone visual demo:

```text
http://127.0.0.1:8020/dark-pattern.html
```

It includes retention misdirection, preselected paid add-on, and bundled marketing-consent cases. The checkbox cases can be toggled to show the risk changing immediately.

Run:

```powershell
.\scripts\Start-JudgeDemo.ps1
```

Open:

```text
http://127.0.0.1:8020/navigation.html
```

## Windows executable

Build the self-contained launcher:

```powershell
.\scripts\Build-NavigationExe.ps1
.\scripts\Test-NavigationExe.ps1
```

Output:

```text
dist\EGL-Navigation-MVP.exe
```

Double-clicking the executable starts the bundled FastAPI server, opens the Navigation MVP in the default browser, and shows a native Windows status window. Pressing **OK** in that window stops the local server. The executable contains the public demo web files and fixture data, but no local `.env` or API keys.

## Deliberate MVP boundary

- The included app and route are synthetic and are not presented as a current path for a real service.
- The browser page simulates the element tree that a future Android AccessibilityService will supply.
- Upstage route retrieval and K-EXAONE semantic fallback can replace the local route repository behind the same API contract.
- Real-app automation, automatic clicks, and irreversible action execution are outside this MVP.
