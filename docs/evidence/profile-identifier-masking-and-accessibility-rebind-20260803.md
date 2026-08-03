# Profile Identifier Masking and Accessibility Rebind — 2026-08-03

## Scope

- Integration commit: `36a4abe`
- Device: Samsung SM-S936N, Android 16, `ko-KR`
- APK SHA-256: `70C14240B60029D2C1FD76A84E66BCA15DFD435C22E4839DDECE82E04026CDB1`
- Production API working directory: `/home/kyle/exitguide/runtime/navigation-api-code-36a4abe/apps/api`
- Production Decision DB remained read-only during this verification.

## Accessibility installation automation

`scripts/Install-NavigationExecutor.ps1` installed the APK with `adb install -r`, preserved the existing enabled-service list, restored ExitGuide when required, and confirmed an actually bound service. The successful result reported:

- `accessibility_enabled=true`
- `accessibility_bound=true`
- `preserved_service_count=2`

No manual Accessibility Settings action was required.

## Tests

- Navigation API decision-memory and runtime tests: passed on N100.
- Android Executor unit tests and `assembleDebug`: passed.
- Runtime storage regression test confirms a profile identifier repeated into sibling candidate fields is redacted before persistence.

## Latest-APK VLM path

Isolated session `navs_626efa01fd7b469f94eaacd380013fa6` used the newly installed APK. Device logs recorded:

- `visual_context ready required=true`
- `decision perception=exaone_4_5 candidates=4 visualScreenshot=true`
- final action `stop_for_user`
- executor did not execute the blocked terminal action

The session used the pre-restart isolated API process, whose older in-memory Runtime serializer retained a profile identifier. The whole isolated session is therefore excluded from Decision Memory promotion. The production API was restarted with the new serializer after its regression test passed. Existing Runtime rows were preserved rather than rewritten.

## Safety result

- Dangerous terminal actions automatically executed: `0`
- Screenshots persisted: `0`
- Isolation validation data promoted: `0`
