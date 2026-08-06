# Android Executor ADB lease automatic pause evidence — 2026-08-06

- device: Samsung SM-G998N (`R3CR60V3DKM`), Android 15
- executor: Navigation Executor 0.6.0 (versionCode 9)
- test mode: controlled heartbeat-loss fault injection; the USB cable remained connected
- target app: YouTube (`com.google.android.youtube`)
- dangerous automatic actions: 0

## Accepted heartbeat

The hidden device monitor sent the explicit receiver action
`com.exitguide.navigation.executor.ADB_HEARTBEAT` every five seconds. The
installed receiver returned `Broadcast completed: result=73`, which is the
executor's acceptance code. No `rejected_unknown_action` log was emitted.

## Automatic pause

The hidden monitor process was stopped while the executor was active, without
sending `ADB_STOP_NAVIGATION`. The executor's own watchdog detected expiry
approximately 15 seconds after the last accepted heartbeat and emitted:

`connection_pause reason=adb_lease_expired connection_error=true`

The persisted executor active flag was cleared, pending operator commands were
discarded, wake-lock was released, and auto-resume remained disabled. No UI
action was selected or executed during this fault-injection interval.

## Contract covered

- ADB heartbeat must be accepted by the installed APK, not merely return an
  `adb` process exit code.
- A missing heartbeat must stop future decisions and delayed action execution.
- Connection loss is recorded as `device_disconnected`/`connection_error`, not
  as navigation failure or candidate absence.
- Reconnection alone never resumes the collection episode; a new explicit
  start command is required.

The exact source commit and APK hash are recorded in `CURRENT_PRIORITY.md`
after the source commit is created and the same commit is rebuilt/reinstalled.
