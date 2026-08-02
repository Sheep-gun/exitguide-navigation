# Decisions

## D001: Android App First

Decision: Build Android-first instead of Chrome-extension-first.

Reason: The contest idea is strongest when the user is making a mobile decision inside apps or mobile web. Chrome extensions are easier to demo but less aligned with the user problem.

Tradeoff: Android has more permission and build complexity. The first MVP avoids live screen control and uses screenshot upload to keep risk low.

## D002: Expo And React Native

Decision: Use Expo with React Native and TypeScript.

Reason: Fastest path to Android UI, APK builds, camera/gallery access, and polished screens within three weeks.

Tradeoff: Some native capabilities such as deep share intent or overlay behavior may require config plugins or a later bare workflow.

## D003: FastAPI Backend

Decision: Use Python FastAPI for AI analysis.

Reason: Python is strong for OCR/AI orchestration, Pydantic schemas, and quick API iteration.

Tradeoff: A separate backend adds deployment work, but it keeps API keys off the device.

## D004: Mock Providers First

Decision: Build mock OCR and LLM providers before real keys.

Reason: The UI, schema, and rule engine can be developed without waiting on external API credentials.

Tradeoff: Real OCR integration may change field quality, so provider outputs must stay normalized.

## D005: Synthetic Screens For Demo

Decision: Use synthetic UI screenshots instead of real company screens for the contest demo.

Reason: Safer for copyright, defamation risk, and repeatable judging.

Tradeoff: Synthetic screens must look realistic enough to prove the product value.

## D006: AndroidControl Only For Public Navigation Priors

Decision: Use AndroidControl demonstrations as the only public dataset prior for Universal Navigation. Do not use Rico or MobileViews.

Reason: AndroidControl directly pairs a high-level user goal with step instructions, accessibility observations, and actions. That structure is closer to EGL's `goal → next function` problem than a large screen corpus without task intent.

Tradeoff: AndroidControl does not guarantee robust behavior on unseen apps. EGL therefore treats retrieved demonstrations as cross-app functional hints, keeps the live accessibility screen as the source of truth, refuses ambiguous choices, and continues accumulating its own successful transition graph.

## D007: Final-Destination-First Function Graph Exploration

Decision: Convert the user's purpose to a canonical terminal function before navigation. If an exact app/version/locale verified route is absent, explore safe menu branches under a strict time/action/depth budget and persist the discovered route as untrusted `shadow` evidence. Independent clean validations promote it through `verified_candidate` and `verified`; only the configured repeated performance gate may promote it to `trusted`. Every grade remains retrieval evidence rather than a replay command.

Reason: Greedy next-button prediction can drift without knowing the destination. A terminal function and explicit DFS path let EGL compare branches, backtrack, reuse discoveries, and detect UI changes while keeping the user's original purpose stable.

Tradeoff: The first encounter takes longer than a prebuilt route and cannot enumerate login-gated, unlabeled Canvas, or external browser screens. A verified candidate can shorten later runs, but only for the exact app version and only while its semantic screens continue to match.

## D008: Automation Exists Only Inside The Exploration Sandbox

Decision: Allow AccessibilityService click/back only while `operation_mode=explore` and only when the server returns `safe_to_execute=true` for a low-risk, non-state-changing, non-checkable function. The same guard applies to verified-candidate reuse, capped at two automatic intermediate clicks. Never automate terminal, payment, deletion, cancellation, refund, consent, permission, switch, radio, checkbox, or text-input actions. A route mismatch invalidates the candidate within two observations and resumes generic exploration.

Reason: Automatic graph discovery materially shortens setup for unseen apps, but the visible route and final state change must remain under user control. Server and device both enforce the same boundary so neither a model mistake nor a delayed response is sufficient to click.

Tradeoff: Some custom controls will reject accessibility clicks and are recorded as failed attempts. EGL then tries another safe branch or stops instead of falling back to unrestricted coordinate automation.
