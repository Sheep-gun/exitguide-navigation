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

The forced second-pass path was subsequently verified on X and is recorded in `x-vlm-and-state-change-safety-device-20260803.md`.

## Account-hub priority and full route rerun

- Netflix version: `9.77.0 build 9 64328+64328`
- Navigation API commit: `3c49a52`
- Executor APK rebuilt from `3c49a52`; SHA-256 remained `45BE8C24E42AF3AB2E778E0BFBC1144CE6C938FAFF5A078586F0FD8925F89FFC`, identical to the installed artifact
- Successful runtime session: `navs_7f48b731e5b5485bab18159ccd584be3`

Two preceding collection attempts exposed a general ranking problem rather than an app-specific route problem:

1. The visible `계정` candidate was correctly inferred as `account.hub=0.96` and ranked first.
2. The K² plan also allowed lower-priority `profile.hub`, so the semantic fast path treated the screen as ambiguous and delegated to Solar.
3. Solar failed closed after the normal visual re-observation wait; no dangerous action ran.
4. `3c49a52` changed semantic fast-path resolution to respect K² target-role order. Ambiguity is now evaluated within the highest-priority visible role, while multiple candidates for the same role still require the planner.

The exact recorded screen replay selected candidate `a11y_69e34fc267c9f884bde5` (`계정`). On the real device the same candidate was then clicked by `semantic_intermediate_role_fast_path` without Solar.

The successful episode ended with:

- `계정` candidate selected by semantic fast path
- account page entered
- four bounded `scroll(down)` actions on the account page
- final observation `destination_reached`
- visible `멤버십 해지` candidate `a11y_d58ad4e05af6ee045883`
- final candidate `selected=0`
- dangerous/final clicks: 0
- Executor `active=false` with status `목적지에 도달했습니다. 최종 행동은 사용자가 직접 수행하세요.`

The intermediate `위로 이동` step is retained in Runtime DB for failure analysis but is not a positive Decision Memory promotion candidate. Only the verified account-hub entry and bounded destination scroll decisions are candidates for promotion after privacy and duplicate checks.
