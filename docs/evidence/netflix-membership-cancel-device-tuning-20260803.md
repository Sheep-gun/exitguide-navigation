# Netflix membership.cancel device tuning — 2026-08-03

## Scope

- Device: Samsung SM-S936N, Android 16, ko-KR
- App: Netflix `com.netflix.mediaclient`, `9.76.0 build 10 64304+64304`
- Navigation API commit: `adde9c4`
- Executor APK commit: `adde9c4`
- Local/device APK SHA-256: `E51F9D2D4D2E2F0EB63BE9AFB8DAAF124CA82B9E5D3DA84A8A3CE4D9BADDE2AE`
- Runtime session: `navs_9f46f76e5127458fab9de9174ea548c0`
- Goal: `membership.cancel`

## Observed calibration sequence

1. The account page already matched part of the destination signature (`0.35`) and exposed an Accessibility scrollable node.
2. The API selected `scroll(down)` through `semantic_destination_scroll_fast_path` without Solar Pro 4 or EXAONE 4.5.
3. The Executor reported `executor_action_succeeded=true` and `screen_changed=true`.
4. The same bounded rule selected one more `scroll(down)` without a model call.
5. The second observation raised the destination match from `0.35` to `0.70` and returned `destination_reached`.
6. The Executor stopped before the visible membership-cancellation action.

## Result

- Runtime session status: `reached`
- Safe scrolls: 2
- Automatic clicks in the final verification session: 0
- VLM calls in the final verification session: 0
- Solar calls in the final verification session: 0
- Connection errors: 0
- Dangerous actions automatically executed: 0
- Stored screenshots: 0; temporary local inspection captures were sent to the Windows recycle bin after inspection.

## Remaining affected verification

Commit `adde9c4` changed the initial visual-reasoning order so Accessibility/DB receives the first decision opportunity. The forced second-pass path (`visual_reobserve_required` → masked screenshot/OCR → EXAONE 4.5 → existing candidate ID validation) was not exercised in this final Netflix fast-path episode. Completion conditions 4 and 5 therefore remain pending until one genuinely ambiguous, safe collection-app screen triggers that path.
