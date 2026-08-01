$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$MobileRoot = Join-Path $RepoRoot "apps/mobile"
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$Script = @'
from pathlib import Path
import json
import sys

from PIL import Image

mobile_root = Path(sys.argv[1])
app_json = json.loads((mobile_root / "app.json").read_text(encoding="utf-8"))
eas_json = json.loads((mobile_root / "eas.json").read_text(encoding="utf-8"))
package_json = json.loads((mobile_root / "package.json").read_text(encoding="utf-8"))
overlay_plugin = (mobile_root / "plugins" / "withExitGuideOverlay.js").read_text(encoding="utf-8")
overlay_controller = (mobile_root / "src" / "hooks" / "useExitGuideOverlayController.ts").read_text(encoding="utf-8")
generated_accessibility = (
    mobile_root
    / "android"
    / "app"
    / "src"
    / "main"
    / "java"
    / "com"
    / "exitguide"
    / "ai"
    / "overlay"
    / "ExitGuideAccessibilityService.java"
).read_text(encoding="utf-8")

expo = app_json.get("expo", {})
android = expo.get("android", {})
if android.get("package") != "com.exitguide.ai":
    raise AssertionError("app.json must keep android.package set to com.exitguide.ai")

plugins = expo.get("plugins", [])
if "./plugins/withExitGuideOverlay" not in plugins:
    raise AssertionError("app.json must include the ExitGuide Android overlay plugin")

required_overlay_contracts = [
    "android.permission.BIND_ACCESSIBILITY_SERVICE",
    "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
    "android.permission.QUERY_ALL_PACKAGES",
    '"android:foregroundServiceType": "specialUse|mediaProjection"',
    "android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE",
    "ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE",
    "ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION",
    "pendingTransitionSequence = ++transitionSequenceCounter",
    "clearPendingTransition(submittedTransitionSequence)",
    "elementIdForEvent(event)",
    "indexClickableElements(elements)",
    "ambiguousClickableKeys",
    "nearestClickableElementId",
    "observation response status=",
    "transition queued hasRecommendation=",
    "android:canRetrieveWindowContent=\"true\"",
    "android:canPerformGestures=\"true\"",
    "android:canTakeScreenshot=\"true\"",
    "com.google.mlkit:text-recognition-korean:16.0.1",
    "takeScreenshot(Display.DEFAULT_DISPLAY",
    "appendOcrElements(elements, result)",
    "nearestClickableParent(elements, bounds)",
    "coordinateClickable",
    "dispatchTapAtBounds(cachedBounds)",
    "isSensitiveOcrRegion(elements, bounds)",
    "android:networkSecurityConfig",
    "cleartextTrafficPermitted=\"false\"",
    "<domain includeSubdomains=\"false\">127.0.0.1</domain>",
    "/v1/navigation/agent/observe",
    "/v1/navigation/agent/performance/complete",
    'clientTiming.put("measurement_source", "real_device")',
    'clientTiming.put("exploration_elapsed_ms", explorationElapsedMs)',
    "SystemClock.elapsedRealtime()",
    'request.put("operation_mode", activeOperationMode)',
    'request.put("app_version", appVersion(packageName))',
    'getPackageManager().getPackageInfo(packageName, 0)',
    'String operationMode = "explore"',
    'PREF_START_NONCE',
    'PREF_EXPLORATION_ACTIVE',
    'startNonce = Long.toString(System.currentTimeMillis())',
    'awaitingUserStart',
    'beginNavigationAnalysis()',
    'showReadyMessage();',
    'WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE',
    'automation.optBoolean("safe_to_execute", false)',
    'recommendation.optBoolean("requires_user_confirmation", true)',
    'lastNoOpRescheduledActionCount = -1',
    'actionCount == lastNoOpRescheduledActionCount',
    'suppressed repeated no-op re-observation actionCount=',
    'target.performAction(AccessibilityNodeInfo.ACTION_CLICK)',
    "dispatchGesture(gesture, null, null)",
    '"scroll_forward".equals(action)',
    "performExplorationScroll",
    "dispatchExplorationPageScroll",
    "PAGE_SCROLL_EDGE_MARGIN_RATIO = 0.08f",
    "PAGE_SCROLL_MIN_VIEWPORT_RATIO = 0.30f",
    "PAGE_SCROLL_DURATION_MS = 420L",
    '" overlapRatio=" + (PAGE_SCROLL_EDGE_MARGIN_RATIO * 2f)',
    "ACTION_SCROLL_FORWARD",
    "ValueAnimator.ofFloat",
    "SPINNER_ROTATION_PERIOD_MS = 1800L",
    "SystemClock.uptimeMillis() - spinnerAnimationStartedAtMs",
    "SpinnerTextView",
    'setSpinnerRotation(0f)',
    'canvas.rotate(spinnerRotation, centerX, centerY)',
    'for (int index = 0; index < 12; index += 1)',
    'bubbleParams.width = dp(48)',
    'bubbleParams.height = dp(48)',
    "openExitGuideApp();",
    "getLaunchIntentForPackage(getPackageName())",
    "Intent.FLAG_ACTIVITY_REORDER_TO_FRONT",
    "clearOverlayStatus(Promise promise)",
    '.remove("goalText")',
    '.remove("startNonce")',
    "isNavigationRequestCurrent(submittedGoal, submittedStartNonce)",
    "discarded stale observation after navigation was cleared or restarted",
    "publishOverlayState",
    'EXTRA_FINISHED',
    'finishNavigation(',
    'EXTRA_FINISH_REASON',
    'FINISH_REASON_DESTINATION_REACHED',
    'FINISH_REASON_STOPPED_NOT_FOUND',
    'navigation exploration finished reason=',
    'boolean onScreen = !bounds.isEmpty()',
    'performGlobalAction(GLOBAL_ACTION_BACK)',
    '"guiding".equals(phase)',
    "ExitGuideAccessibilityService",
    'SYSTEM_UI_PACKAGE = "com.android.systemui"',
    "isRelevantAccessibilityEventPackage(packageName)",
    "eventPackageName.equals(activePackageName)",
    "eventPackageName.equals(inFlightPackageName)",
    "suppressed duplicate observation after request failure",
    "markObservationRequestFailed(treeSignature)",
    "clearObservationRequestFailure()",
    "REQUEST_FAILURE_RETRY_DELAY_MS = 2500L",
]
for contract in required_overlay_contracts:
    if contract not in overlay_plugin:
        raise AssertionError(f"overlay plugin is missing universal navigation contract: {contract}")
for contract in [
    'SYSTEM_UI_PACKAGE = "com.android.systemui"',
    "isRelevantAccessibilityEventPackage(packageName)",
    "eventPackageName.equals(activePackageName)",
    "eventPackageName.equals(inFlightPackageName)",
    "suppressed duplicate observation after request failure",
    "markObservationRequestFailed(treeSignature)",
    "clearObservationRequestFailure()",
    "REQUEST_FAILURE_RETRY_DELAY_MS = 2500L",
    'request.put("app_version", appVersion(packageName))',
    'getPackageManager().getPackageInfo(packageName, 0)',
]:
    if contract not in generated_accessibility:
        raise AssertionError(
            f"generated accessibility service is out of sync with the overlay plugin: {contract}"
        )
if overlay_plugin.count("markObservationRequestFailed(treeSignature)") != 2:
    raise AssertionError("both HTTP and transport observation failures must enter retry suppression")
if generated_accessibility.count("markObservationRequestFailed(treeSignature)") != 2:
    raise AssertionError("generated service must suppress retries for HTTP and transport failures")
event_handler_start = overlay_plugin.find("public void onAccessibilityEvent(AccessibilityEvent event)")
event_handler_end = overlay_plugin.find("public void onInterrupt()", event_handler_start)
event_handler = overlay_plugin[event_handler_start:event_handler_end]
event_filter = event_handler.find("isRelevantAccessibilityEventPackage(packageName)")
event_metadata = event_handler.find("lastActivityName =")
event_schedule = event_handler.rfind("scheduleAnalysis(false)")
if event_handler_start < 0 or min(event_filter, event_metadata, event_schedule) < 0:
    raise AssertionError("accessibility event filtering contract is incomplete")
if not event_filter < event_metadata < event_schedule:
    raise AssertionError("irrelevant package events must be rejected before metadata or queue mutation")
duplicate_failure_guard = (
    'if (!force && pendingPerformedElementId.length() == 0\n'
    '          && treeSignature.equals(lastFailedTreeSignature))'
)
if duplicate_failure_guard not in overlay_plugin or duplicate_failure_guard not in generated_accessibility:
    raise AssertionError(
        "failed-screen suppression must still permit forced requests, click transitions, and changed trees"
    )
if overlay_plugin.count("target.performAction(AccessibilityNodeInfo.ACTION_CLICK)") != 1:
    raise AssertionError("automatic click must exist only in the guarded exploration executor")
if "|| !\"low\".equals(risk) || confirmation" not in overlay_plugin:
    raise AssertionError("automatic exploration must reject risky or confirmation-required actions")
no_op_branch = overlay_plugin.find('if ("none".equals(action) && "exploring".equals(phase))')
no_op_guard = overlay_plugin.find("actionCount == lastNoOpRescheduledActionCount", no_op_branch)
no_op_schedule = overlay_plugin.find("schedulePostAutomationAnalysis();", no_op_branch)
if no_op_branch < 0 or no_op_guard < 0 or no_op_schedule < 0 or no_op_guard > no_op_schedule:
    raise AssertionError("safe no-op re-observation must be client-bounded before it is rescheduled")
if '"destination_reached".equals(phase)' not in overlay_plugin:
    raise AssertionError("guidance transition must disable exploration automation")
stopped_branch = overlay_plugin.find('if ("stopped".equals(phase))')
if stopped_branch < 0 or 'FINISH_REASON_STOPPED_NOT_FOUND' not in overlay_plugin[stopped_branch:stopped_branch + 320]:
    raise AssertionError("failed exploration must finish the overlay instead of restarting a new session")
if "finished at destination" in overlay_plugin:
    raise AssertionError("failed exploration logging must never claim that a destination was reached")
if "Promise.race" in overlay_controller or "setTimeout" in overlay_controller:
    raise AssertionError("overlay controls must not rely on background-suspended timers to release busy state")
for forbidden_busy_transition in ('setStartBusy(true)', 'setStopBusy(true)'):
    if forbidden_busy_transition in overlay_controller:
        raise AssertionError("overlay controls must not enter a busy UI state before backgrounding")
for contract in [
    'releaseOperation();',
    'releaseOperation("start");',
    'releaseOperation("stop");',
    '.catch((error: unknown)',
]:
    if contract not in overlay_controller:
        raise AssertionError(f"overlay controller is missing immediate busy/error contract: {contract}")
if 'showToast("해당 앱을 열고, 시작을 눌러주세요.")' in overlay_plugin:
    raise AssertionError("ready guidance must be shown only in the overlay bubble, not duplicated as a toast")
if "guidanceView" in overlay_plugin or "showGuidance" in overlay_plugin:
    raise AssertionError("large guidance cards must not obscure the target app")
if 'bubble.setText("↻")' in overlay_plugin:
    raise AssertionError("the legacy glyph spinner must not replace the fixed-center 12-bar loader")
click_handler = overlay_plugin.find("bubble.setOnClickListener")
drag_handler = overlay_plugin.find("private void attachDragHandler", click_handler)
if click_handler < 0 or drag_handler < 0:
    raise AssertionError("floating icon click handler was not generated")
click_contract = overlay_plugin[click_handler:drag_handler]
if "if (awaitingUserStart)" not in click_contract or "beginNavigationAnalysis();" not in click_contract:
    raise AssertionError("ready-state floating icon must start navigation only after the user taps it")
if "openExitGuideApp();" not in click_contract:
    raise AssertionError("active floating icon must still return to ExitGuide when tapped")
if 'mainApplication.$["android:usesCleartextTraffic"] = "true"' in overlay_plugin:
    raise AssertionError("overlay plugin must not enable cleartext traffic globally")
capture_branch = overlay_plugin.find("if (ACTION_CAPTURE_RESULT.equals(action))")
overlay_foreground = overlay_plugin.find("startOverlayForeground();", capture_branch)
if capture_branch < 0 or overlay_foreground < 0:
    raise AssertionError("overlay plugin must split navigation and MediaProjection foreground startup")
if "clearPendingTransition();\n          publishOverlayState" in overlay_plugin:
    raise AssertionError("slow responses must not clear newer click transitions unconditionally")

asset_paths = [
    expo.get("icon"),
    expo.get("splash", {}).get("image"),
    android.get("adaptiveIcon", {}).get("foregroundImage"),
]
for asset_path in asset_paths:
    if not asset_path:
        raise AssertionError("app.json is missing a required image asset path")
    asset = mobile_root / asset_path
    if not asset.exists():
        raise AssertionError(f"missing app asset: {asset_path}")
    with Image.open(asset) as image:
        if image.size != (1024, 1024):
            raise AssertionError(f"{asset_path} must be 1024x1024, got {image.size}")

expo_version = package_json.get("dependencies", {}).get("expo", "")
if not expo_version.startswith("~54."):
    raise AssertionError("package.json should stay on Expo SDK 54 for the current mobile baseline")

build = eas_json.get("build", {})
if build.get("preview", {}).get("android", {}).get("buildType") != "apk":
    raise AssertionError("eas preview profile must build an Android APK")
if build.get("production", {}).get("android", {}).get("buildType") != "app-bundle":
    raise AssertionError("eas production profile must build an Android App Bundle")

print("Android config checks passed.")
'@

$Script | & $Python - $MobileRoot
if ($LASTEXITCODE -ne 0) {
  throw "Android config checks failed with exit code $LASTEXITCODE"
}
