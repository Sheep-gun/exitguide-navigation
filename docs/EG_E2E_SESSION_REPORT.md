# EG physical-session report

`Report-EgNavigationSession.py` reads the navigation SQLite database in
read-only mode and reports one physical ExitGuide navigation session.  Its JSON
contains only timings, counters, fixed lifecycle categories, and hashed session
references.  It does not emit goal text, screen fingerprints, element keys,
labels, route steps, screenshots, XML, or secrets.

Capture the baseline immediately before starting a physical test:

```powershell
apps\api\.venv\Scripts\python.exe scripts\Report-EgNavigationSession.py `
  --capture-baseline
```

The returned value is the maximum `navigation_sessions.rowid` at that moment.
After the test, report the single matching session created after that row:

```powershell
apps\api\.venv\Scripts\python.exe scripts\Report-EgNavigationSession.py `
  --baseline-rowid 12 `
  --app-package com.google.android.youtube
```

If multiple physical sessions for the package were created after the baseline,
pass the exact client session ID with `--session-id`.  The ID is used only for
selection and is represented in output by a SHA-256-derived `session_ref`.

The report distinguishes approved route reuse (`route_cache`), learned graph
cache use, function-graph exploration, deterministic fallback, and EXAONE
fallback.  A newly discovered route is counted only when its app/version,
goal key, target function, and creation interval match the selected session;
the output also confirms whether it remains shadow/provisional.

Run the focused test with:

```powershell
Push-Location apps\api
.\.venv\Scripts\python.exe tests\navigation_session_report_unit.py
Pop-Location
```
