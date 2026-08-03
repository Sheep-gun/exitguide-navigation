package com.exitguide.navigation.executor;

import android.accessibilityservice.AccessibilityService;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.ColorSpace;
import android.hardware.HardwareBuffer;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.util.Log;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.Locale;
import java.util.List;
import java.util.UUID;

public final class ExitGuideAccessibilityService extends AccessibilityService {
    private interface VisualContextCallback {
        void onReady(String dataUrl, boolean visualReasoningRequired);
    }

    private static final String LOG_TAG = "ExitGuideNavigationExecutor";
    private static final String SYSTEM_UI_PACKAGE = "com.android.systemui";
    private static final long EVENT_DEBOUNCE_MS = 700;
    private static final long MAX_EVENT_DEBOUNCE_MS = 2_000;
    private static final long OBSERVATION_DELAY_MS = 1_200;
    private static final long OBSERVATION_QUIET_WINDOW_MS = 350;
    private static final long MAX_OBSERVATION_SETTLE_MS = 3_500;
    private static final int MAX_ACTIONS = 15;
    private static final long MAX_EPISODE_DURATION_MS = 10 * 60 * 1_000L;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final NavigationApiClient apiClient = new NavigationApiClient();
    private final EpisodeGenerationGuard episodeGuard = new EpisodeGenerationGuard();
    private final DecisionDebounceWindow decisionDebounceWindow =
            new DecisionDebounceWindow(MAX_EVENT_DEBOUNCE_MS);
    private final VisualScreenAugmenter visualAugmenter = new VisualScreenAugmenter();

    private AccessibilityScreenReader screenReader;
    private boolean inFlight;
    private int stepOrdinal;
    private String sessionId = "";
    private String sessionAppPackage = "";
    private String lastActivityName = "";
    private Runnable pendingDecision;
    private PowerManager.WakeLock screenWakeLock;
    private long episodeStartedAtElapsed;
    private long lastRelevantEventElapsed;
    private boolean forceVisualNextDecision;

    private final BroadcastReceiver configurationReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String previousSessionId = sessionId;
            resetSession();
            if (ExecutorPreferences.active(ExitGuideAccessibilityService.this)) {
                holdScreenAwake();
                verifyApiAndSchedule();
            } else {
                cancelPending();
                releaseScreenAwake();
                requestSessionStop(previousSessionId);
            }
        }
    };

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        screenReader = new AccessibilityScreenReader(getResources().getDisplayMetrics());
        IntentFilter filter = new IntentFilter(ExecutorPreferences.ACTION_CONFIGURATION_CHANGED);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(configurationReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(configurationReceiver, filter);
        }
        publish("접근성 서비스가 준비되었습니다.");
        if (ExecutorPreferences.active(this)) {
            holdScreenAwake();
            verifyApiAndSchedule();
        }
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null || !ExecutorPreferences.active(this)) {
            return;
        }
        String packageName = text(event.getPackageName());
        if (!isRelevantAccessibilityEventPackage(packageName)) {
            return;
        }
        lastActivityName = text(event.getClassName());
        lastRelevantEventElapsed = SystemClock.elapsedRealtime();
        if (inFlight) {
            return;
        }
        scheduleDecision(EVENT_DEBOUNCE_MS);
    }

    private boolean isRelevantAccessibilityEventPackage(String eventPackageName) {
        if (eventPackageName == null
                || eventPackageName.isEmpty()
                || getPackageName().equals(eventPackageName)
                || SYSTEM_UI_PACKAGE.equals(eventPackageName)) {
            return false;
        }
        AccessibilityNodeInfo activeRoot = getRootInActiveWindow();
        if (activeRoot == null) {
            return false;
        }
        try {
            String activePackageName = text(activeRoot.getPackageName());
            return eventPackageName.equals(activePackageName)
                    && !getPackageName().equals(activePackageName)
                    && !SYSTEM_UI_PACKAGE.equals(activePackageName);
        } finally {
            activeRoot.recycle();
        }
    }

    @Override
    public void onInterrupt() {
        publish("접근성 관찰이 중단되었습니다. 다시 관찰합니다.");
        scheduleDecision(1_000);
    }

    @Override
    public void onDestroy() {
        cancelPending();
        releaseScreenAwake();
        try {
            unregisterReceiver(configurationReceiver);
        } catch (IllegalArgumentException ignored) {
            // Service startup did not finish.
        }
        visualAugmenter.close();
        apiClient.close();
        super.onDestroy();
    }

    private void verifyApiAndSchedule() {
        long generation = episodeGuard.current();
        holdScreenAwake();
        publish("Navigation API 상태를 확인하는 중입니다.");
        apiClient.get(
                ExecutorPreferences.apiBaseUrl(this),
                "/v1/navigation/status",
                new NavigationApiClient.Callback() {
                    @Override
                    public void onSuccess(JSONObject response) {
                        if (!acceptsCallback(generation)) {
                            return;
                        }
                        if (!response.optBoolean("ready", false)) {
                            stop("Navigation API가 준비되지 않았습니다.");
                            return;
                        }
                        publish("Navigation API 연결됨: " + response.optString("serving_mode", "unknown"));
                        scheduleDecision(300);
                    }

                    @Override
                    public void onFailure(String failureClass, String detail) {
                        if (!acceptsCallback(generation)) {
                            return;
                        }
                        publish("Navigation API 연결 오류(" + failureClass + "). 잠시 후 재확인합니다.");
                        scheduleDecision(2_000);
                    }
                }
        );
    }

    private void scheduleDecision(long delayMs) {
        if (!ExecutorPreferences.active(this) || inFlight) {
            return;
        }
        long boundedDelayMs = decisionDebounceWindow.boundedDelay(
                SystemClock.elapsedRealtime(),
                delayMs
        );
        if (pendingDecision != null) {
            handler.removeCallbacks(pendingDecision);
        }
        pendingDecision = this::requestDecision;
        handler.postDelayed(pendingDecision, boundedDelayMs);
    }

    private void cancelPending() {
        if (pendingDecision != null) {
            handler.removeCallbacks(pendingDecision);
            pendingDecision = null;
        }
        decisionDebounceWindow.reset();
    }

    private void requestDecision() {
        pendingDecision = null;
        decisionDebounceWindow.reset();
        if (!ExecutorPreferences.active(this) || inFlight) {
            return;
        }
        if (episodeStartedAtElapsed == 0L) {
            episodeStartedAtElapsed = SystemClock.elapsedRealtime();
        }
        if (stepOrdinal >= MAX_ACTIONS) {
            stop("안전 한도 15회에 도달했습니다. 현재 화면을 사용자가 확인해야 합니다.");
            return;
        }
        if (SystemClock.elapsedRealtime() - episodeStartedAtElapsed >= MAX_EPISODE_DURATION_MS) {
            stop("안전 시간 한도 10분에 도달했습니다. 현재 화면을 사용자가 확인해야 합니다.");
            return;
        }
        AccessibilityScreenReader.ScreenSnapshot snapshot = currentSnapshot();
        if (snapshot == null) {
            publish("현재 화면의 접근성 구조를 읽지 못했습니다. 잠시 후 다시 관찰합니다.");
            scheduleDecision(1_000);
            return;
        }
        Log.i(
                LOG_TAG,
                "screen_observed package=" + snapshot.appPackage
                        + " nodes=" + (
                                snapshot.payload.optJSONArray("nodes") == null
                                        ? 0
                                        : snapshot.payload.optJSONArray("nodes").length()
                        )
                        + " candidates=" + snapshot.bindings.size()
        );
        long generation = episodeGuard.current();
        inFlight = true;
        boolean forceVisualReasoning = forceVisualNextDecision;
        forceVisualNextDecision = false;
        prepareVisualContext(snapshot, forceVisualReasoning, (dataUrl, visualReasoningRequired) -> {
            if (!acceptsCallback(generation)) {
                return;
            }
            if (visualReasoningRequired && dataUrl.isEmpty()) {
                inFlight = false;
                stop("시각 판단이 필요한 화면의 안전한 스크린샷을 만들지 못해 중지했습니다.");
                return;
            }
            postDecision(
                    snapshot,
                    emptyToNull(dataUrl),
                    visualReasoningRequired,
                    generation
            );
        });
    }

    private void postDecision(
            AccessibilityScreenReader.ScreenSnapshot snapshot,
            String screenshotDataUrl,
            boolean visualReasoningRequired,
            long generation
    ) {
        if (!acceptsCallback(generation)) {
            return;
        }
        try {
            JSONObject request = new JSONObject();
            request.put("request_id", UUID.randomUUID().toString());
            if (!sessionId.isEmpty()) {
                request.put("session_id", sessionId);
            }
            if (sessionAppPackage.isEmpty()) {
                sessionAppPackage = snapshot.appPackage;
            }
            request.put("app_package", sessionAppPackage);
            request.put("app_version", packageVersion(sessionAppPackage));
            request.put("locale", Locale.getDefault().toLanguageTag());
            request.put("goal_text", ExecutorPreferences.goal(this));
            request.put("step_ordinal", stepOrdinal);
            request.put("visual_reasoning_required", visualReasoningRequired);
            if (screenshotDataUrl != null) {
                request.put("screenshot_data_url", screenshotDataUrl);
            }
            request.put("screen", snapshot.payload);
            publish("다음 안전 행동을 판단하는 중입니다.");
            apiClient.post(
                    ExecutorPreferences.apiBaseUrl(this),
                    "/v1/navigation/decide",
                    request,
                    new NavigationApiClient.Callback() {
                        @Override
                        public void onSuccess(JSONObject response) {
                            if (!acceptsCallback(generation)) {
                                requestSessionStop(response.optString("session_id", ""));
                                return;
                            }
                            handleDecision(response, snapshot, screenshotDataUrl, generation);
                        }

                        @Override
                        public void onFailure(String failureClass, String detail) {
                            if (!acceptsCallback(generation)) {
                                return;
                            }
                            inFlight = false;
                            stop("판단 요청 실패(" + failureClass + "). 화면 탐색 실패로 기록하지 않았습니다.");
                        }
                    }
            );
        } catch (JSONException error) {
            inFlight = false;
            stop("판단 요청을 만들 수 없습니다: " + error.getMessage());
        }
    }

    private void handleDecision(
            JSONObject response,
            AccessibilityScreenReader.ScreenSnapshot beforeSnapshot,
            String beforeScreenshot,
            long generation
    ) {
        if (!acceptsCallback(generation)) {
            requestSessionStop(response.optString("session_id", ""));
            return;
        }
        sessionId = response.optString("session_id", sessionId);
        Log.i(
                LOG_TAG,
                "decision perception=" + response.optString("perception_provider", "unknown")
                        + " candidates=" + beforeSnapshot.bindings.size()
                        + " visualScreenshot=" + (beforeScreenshot != null)
        );
        String decisionId = response.optString("decision_id", "");
        JSONObject action = response.optJSONObject("action");
        if (decisionId.isEmpty() || action == null) {
            inFlight = false;
            stop("Navigation API 응답에 decision_id 또는 action이 없습니다.");
            return;
        }
        String actionName = action.optString("name", "");
        if (!NavigationSafetyPolicy.isAllowedAction(actionName)) {
            observeDecision(
                    decisionId,
                    beforeSnapshot,
                    beforeScreenshot,
                    generation,
                    false,
                    "blocked",
                    true,
                    "허용되지 않은 행동을 차단했습니다: " + actionName
            );
            return;
        }
        if (response.optBoolean("visual_reobserve_required", false)) {
            if (!"wait_and_observe".equals(actionName)) {
                observeDecision(
                        decisionId,
                        beforeSnapshot,
                        beforeScreenshot,
                        generation,
                        false,
                        "blocked",
                        true,
                        "VLM 재관찰 요청이 클릭 행동과 함께 반환되어 안전하게 차단했습니다."
                );
                return;
            }
            forceVisualNextDecision = true;
            publish("후보가 모호하여 candidate_id 오버레이로 다시 관찰합니다: "
                    + response.optString("visual_reobserve_reason", "visual_context_required"));
        }
        if ("stop_for_user".equals(actionName)) {
            observeDecision(
                    decisionId,
                    beforeSnapshot,
                    beforeScreenshot,
                    generation,
                    false,
                    "blocked",
                    true,
                    "목적지 또는 위험한 최종 행동 앞에서 멈췄습니다. 사용자가 직접 확인하세요."
            );
            return;
        }

        ActionExecution execution = execute(action, beforeSnapshot);
        publish(execution.message);
        long settleDeadline = SystemClock.elapsedRealtime() + MAX_OBSERVATION_SETTLE_MS;
        handler.postDelayed(
                () -> observeWhenSettled(
                        decisionId,
                        beforeSnapshot,
                        beforeScreenshot,
                        generation,
                        execution,
                        settleDeadline
                ),
                "wait_and_observe".equals(actionName) ? 1_600 : OBSERVATION_DELAY_MS
        );
    }

    private void observeWhenSettled(
            String decisionId,
            AccessibilityScreenReader.ScreenSnapshot beforeSnapshot,
            String beforeScreenshot,
            long generation,
            ActionExecution execution,
            long settleDeadline
    ) {
        if (!acceptsCallback(generation)) {
            return;
        }
        long now = SystemClock.elapsedRealtime();
        long quietFor = now - lastRelevantEventElapsed;
        if (lastRelevantEventElapsed > 0L
                && quietFor < OBSERVATION_QUIET_WINDOW_MS
                && now < settleDeadline) {
            handler.postDelayed(
                    () -> observeWhenSettled(
                            decisionId,
                            beforeSnapshot,
                            beforeScreenshot,
                            generation,
                            execution,
                            settleDeadline
                    ),
                    Math.max(50L, OBSERVATION_QUIET_WINDOW_MS - quietFor)
            );
            return;
        }
        observeDecision(
                decisionId,
                beforeSnapshot,
                beforeScreenshot,
                generation,
                execution.succeeded,
                execution.observedSignal,
                false,
                ""
        );
    }

    private ActionExecution execute(
            JSONObject action,
            AccessibilityScreenReader.ScreenSnapshot snapshot
    ) {
        String name = action.optString("name", "");
        switch (name) {
            case "click":
                return clickCandidate(action.optString("candidate_id", ""), snapshot);
            case "scroll":
                return scroll(action.optString("direction", "down"));
            case "back":
                return new ActionExecution(
                        performGlobalAction(GLOBAL_ACTION_BACK),
                        "none",
                        "뒤로가기를 실행했습니다."
                );
            case "wait_and_observe":
                return new ActionExecution(true, "none", "화면 변화를 기다립니다.");
            default:
                return new ActionExecution(false, "blocked", "허용되지 않은 행동을 차단했습니다.");
        }
    }

    private ActionExecution clickCandidate(
            String candidateId,
            AccessibilityScreenReader.ScreenSnapshot snapshot
    ) {
        AccessibilityScreenReader.CandidateBinding binding = snapshot.bindings.get(candidateId);
        if (binding == null) {
            return new ActionExecution(false, "blocked", "현재 화면에 없는 후보 ID를 차단했습니다.");
        }
        if (!"low".equals(binding.riskLevel)) {
            return new ActionExecution(false, "blocked", "위험하거나 입력 상태를 바꾸는 후보를 차단했습니다.");
        }
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) {
            return new ActionExecution(false, "blocked", "클릭 직전 현재 화면을 다시 읽지 못했습니다.");
        }
        AccessibilityNodeInfo node = null;
        try {
            node = screenReader.resolve(root, binding);
            if (node == null || !node.isVisibleToUser() || !node.isEnabled() || !node.isClickable()) {
                return new ActionExecution(false, "blocked", "후보가 바뀌어 클릭을 취소했습니다.");
            }
            if (!"low".equals(NavigationSafetyPolicy.riskLevel(node, binding.semanticText))) {
                return new ActionExecution(false, "blocked", "클릭 직전 안전 재검사에서 후보를 차단했습니다.");
            }
            boolean succeeded = node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            Log.i(
                    LOG_TAG,
                    "action_execution name=click candidate_id=" + candidateId
                            + " executor_action_succeeded=" + succeeded
            );
            return new ActionExecution(
                    succeeded,
                    succeeded ? "none" : "blocked",
                    succeeded ? "후보 ID를 안전하게 클릭했습니다." : "Accessibility 클릭이 거절되었습니다."
            );
        } finally {
            if (node != null && !binding.path.isEmpty()) {
                node.recycle();
            }
            root.recycle();
        }
    }

    private ActionExecution scroll(String direction) {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        AccessibilityNodeInfo scrollable = findScrollable(root);
        if (scrollable == null) {
            if (root != null) {
                root.recycle();
            }
            return new ActionExecution(false, "blocked", "스크롤 가능한 영역을 찾지 못했습니다.");
        }
        try {
            int action = "up".equals(direction)
                    ? AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
                    : AccessibilityNodeInfo.ACTION_SCROLL_FORWARD;
            boolean succeeded = scrollable.performAction(action);
            Log.i(
                    LOG_TAG,
                    "action_execution name=scroll direction=" + direction
                            + " executor_action_succeeded=" + succeeded
            );
            return new ActionExecution(
                    succeeded,
                    succeeded ? "none" : "blocked",
                    succeeded ? "Accessibility 스크롤을 실행했습니다." : "Accessibility 스크롤이 거절되었습니다."
            );
        } finally {
            if (scrollable != root) {
                scrollable.recycle();
            }
            if (root != null) {
                root.recycle();
            }
        }
    }

    private AccessibilityNodeInfo findScrollable(AccessibilityNodeInfo node) {
        if (node == null) {
            return null;
        }
        if (node.isVisibleToUser() && node.isScrollable()) {
            return node;
        }
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo child = node.getChild(index);
            if (child == null) {
                continue;
            }
            AccessibilityNodeInfo found = findScrollable(child);
            if (found != null) {
                if (found != child) {
                    child.recycle();
                }
                return found;
            }
            child.recycle();
        }
        return null;
    }

    private void observeDecision(
            String decisionId,
            AccessibilityScreenReader.ScreenSnapshot beforeSnapshot,
            String beforeScreenshot,
            long generation,
            boolean executionSucceeded,
            String executionSignal,
            boolean stopAfterObserve,
            String stopMessage
    ) {
        if (!acceptsCallback(generation)) {
            return;
        }
        AccessibilityScreenReader.ScreenSnapshot afterSnapshot = currentSnapshot();
        if (afterSnapshot == null) {
            postUnobservedOutcome(
                    decisionId, generation, executionSucceeded, stopAfterObserve, stopMessage
            );
            return;
        }
        String detectedSignal = ObservationSignalDetector.detect(
                executionSignal,
                beforeSnapshot.appPackage,
                afterSnapshot.appPackage,
                afterSnapshot.payload.toString()
        );
        String observedSignal = "none".equals(detectedSignal)
                && afterSnapshot.popupWindowAmbiguous
                && !beforeSnapshot.popupWindowAmbiguous
                ? "popup"
                : detectedSignal;
        Log.i(
                LOG_TAG,
                "post_action_observation executor_action_succeeded=" + executionSucceeded
                        + " screen_changed="
                        + !beforeSnapshot.payload.toString().equals(afterSnapshot.payload.toString())
                        + " observed_signal=" + observedSignal
        );
        prepareVisualContext(
                afterSnapshot,
                beforeScreenshot != null,
                (afterScreenshot, ignoredVisualReasoningRequired) -> {
            if (!acceptsCallback(generation)) {
                return;
            }
            try {
                JSONObject request = new JSONObject();
                request.put("request_id", UUID.randomUUID().toString());
                request.put("decision_id", decisionId);
                request.put("connectivity_status", "observed");
                request.put("observed_signal", observedSignal);
                request.put("execution_succeeded", executionSucceeded);
                if (beforeScreenshot != null) {
                    request.put("before_screenshot_data_url", beforeScreenshot);
                }
                if (!afterScreenshot.isEmpty()) {
                    request.put("after_screenshot_data_url", afterScreenshot);
                }
                request.put("next_screen", afterSnapshot.payload);
                postObservation(request, generation, stopAfterObserve, stopMessage);
            } catch (JSONException error) {
                inFlight = false;
                stop("관찰 요청을 만들 수 없습니다: " + error.getMessage());
            }
        });
    }

    private void postUnobservedOutcome(
            String decisionId,
            long generation,
            boolean executionSucceeded,
            boolean stopAfterObserve,
            String stopMessage
    ) {
        if (!acceptsCallback(generation)) {
            return;
        }
        try {
            JSONObject request = new JSONObject();
            request.put("request_id", UUID.randomUUID().toString());
            request.put("decision_id", decisionId);
            request.put("connectivity_status", "device_disconnected");
            request.put("observed_signal", "none");
            request.put("execution_succeeded", executionSucceeded);
            postObservation(request, generation, stopAfterObserve, stopMessage);
        } catch (JSONException error) {
            inFlight = false;
            stop("기기 관찰 오류를 기록하지 못했습니다.");
        }
    }

    private void postObservation(
            JSONObject request,
            long generation,
            boolean stopAfterObserve,
            String stopMessage
    ) {
        if (!acceptsCallback(generation)) {
            return;
        }
        apiClient.post(
                ExecutorPreferences.apiBaseUrl(this),
                "/v1/navigation/observe",
                request,
                new NavigationApiClient.Callback() {
                    @Override
                    public void onSuccess(JSONObject response) {
                        if (!acceptsCallback(generation)) {
                            return;
                        }
                        inFlight = false;
                        stepOrdinal++;
                        String outcome = response.optString("outcome_type", "unknown");
                        String progress = response.optString("progress_label", "unknown");
                        String sessionStatus = response.optString("session_status", "active");
                        forceVisualNextDecision = forceVisualNextDecision || requiresVisualRecovery(
                                outcome,
                                progress,
                                response.optJSONObject("recovery_action") == null
                                        ? ""
                                        : response.optJSONObject("recovery_action")
                                                .optString("name", "")
                        );
                        publish("관찰 결과: " + outcome + " / " + progress);
                        Log.i(
                                LOG_TAG,
                                "observe_result planner_decision_succeeded="
                                        + response.optBoolean("planner_decision_succeeded", false)
                                        + " executor_action_succeeded="
                                        + response.optString("executor_action_succeeded", "null")
                                        + " screen_changed="
                                        + response.optString("screen_changed", "null")
                                        + " navigation_progressed="
                                        + response.optString("navigation_progressed", "null")
                                        + " connection_error="
                                        + response.optBoolean("connection_error", false)
                        );
                        if (stopAfterObserve
                                || "destination_reached".equals(outcome)
                                || "stopped".equals(sessionStatus)
                                || "reached".equals(sessionStatus)) {
                            String terminalMessage = stopMessage;
                            if (terminalMessage.isEmpty()) {
                                terminalMessage = "stopped".equals(sessionStatus)
                                        ? "안전 경계가 감지되어 사용자의 확인이 필요합니다."
                                        : "목적지에 도달했습니다. 최종 행동은 사용자가 직접 수행하세요.";
                            }
                            stop(terminalMessage);
                            return;
                        }
                        JSONObject recovery = response.optJSONObject("recovery_action");
                        if (recovery != null) {
                            String recoveryName = recovery.optString("name", "reselect");
                            publish("복구 필요: " + recoveryName
                                    + ". 다음 판단에서 안전하게 반영합니다.");
                        }
                        scheduleDecision(500);
                    }

                    @Override
                    public void onFailure(String failureClass, String detail) {
                        if (!acceptsCallback(generation)) {
                            return;
                        }
                        inFlight = false;
                        stop("관찰 전송 실패(" + failureClass + "). UI 탐색 실패로 오인하지 않고 중지했습니다.");
                    }
                }
        );
    }

    private AccessibilityScreenReader.ScreenSnapshot currentSnapshot() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null || screenReader == null) {
            return null;
        }
        try {
            return screenReader.read(root, lastActivityName, hasMultipleApplicationWindows());
        } catch (JSONException error) {
            publish("접근성 화면 구조화 실패: " + error.getMessage());
            return null;
        } finally {
            root.recycle();
        }
    }

    private boolean hasMultipleApplicationWindows() {
        List<AccessibilityWindowInfo> windows = getWindows();
        if (windows == null || windows.isEmpty()) {
            return false;
        }
        int applicationWindows = 0;
        for (AccessibilityWindowInfo window : windows) {
            if (window != null && window.getType() == AccessibilityWindowInfo.TYPE_APPLICATION) {
                applicationWindows++;
                if (applicationWindows > 1) {
                    return true;
                }
            }
        }
        return false;
    }

    private String packageVersion(String packageName) {
        if (packageName == null || packageName.isEmpty()) {
            return "";
        }
        try {
            PackageInfo info;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                info = getPackageManager().getPackageInfo(
                        packageName,
                        PackageManager.PackageInfoFlags.of(0L)
                );
            } else {
                info = getPackageManager().getPackageInfo(packageName, 0);
            }
            String name = info.versionName == null ? "" : info.versionName;
            return name + "+" + info.getLongVersionCode();
        } catch (PackageManager.NameNotFoundException error) {
            return "";
        }
    }

    private void prepareVisualContext(
            AccessibilityScreenReader.ScreenSnapshot snapshot,
            boolean forceCapture,
            VisualContextCallback callback
    ) {
        boolean visualReasoningRequired = forceCapture || (
                screenReader != null && screenReader.needsVisualReasoning(snapshot)
        );
        if (!forceCapture && !visualReasoningRequired) {
            Log.i(LOG_TAG, "visual_context skipped reason=accessibility_clear");
            VisualScreenAugmenter.redactSnapshotInPlace(snapshot);
            callback.onReady("", false);
            return;
        }
        try {
            takeScreenshot(
                    Display.DEFAULT_DISPLAY,
                    getMainExecutor(),
                    new TakeScreenshotCallback() {
                        @Override
                        public void onSuccess(ScreenshotResult screenshot) {
                            Bitmap bitmap = toSoftwareBitmap(screenshot);
                            if (bitmap == null) {
                                callback.onReady("", visualReasoningRequired);
                                return;
                            }
                            visualAugmenter.augment(bitmap, snapshot, (dataUrl, mergedOcrLines) -> {
                                bitmap.recycle();
                                VisualScreenAugmenter.redactSnapshotInPlace(snapshot);
                                Log.i(
                                        LOG_TAG,
                                        "visual_context ready required=" + visualReasoningRequired
                                                + " ocrMerged=" + mergedOcrLines
                                                + " candidateIds=" + snapshot.bindings.size()
                                );
                                callback.onReady(dataUrl, visualReasoningRequired);
                            });
                        }

                        @Override
                        public void onFailure(int errorCode) {
                            Log.w(LOG_TAG, "screenshot failed code=" + errorCode);
                            VisualScreenAugmenter.redactSnapshotInPlace(snapshot);
                            callback.onReady("", visualReasoningRequired);
                        }
                    }
            );
        } catch (IllegalStateException | SecurityException error) {
            Log.w(LOG_TAG, "screenshot unavailable=" + error.getClass().getSimpleName());
            VisualScreenAugmenter.redactSnapshotInPlace(snapshot);
            callback.onReady("", visualReasoningRequired);
        }
    }

    static boolean requiresVisualRecovery(
            String outcome,
            String progress,
            String recoveryName
    ) {
        if ("no_change".equals(outcome)
                || "wrong_destination".equals(outcome)
                || "popup".equals(outcome)
                || "repeated_screen".equals(outcome)
                || "unchanged".equals(progress)
                || "regressed".equals(progress)) {
            return true;
        }
        return "back".equals(recoveryName) || "wait_and_observe".equals(recoveryName);
    }

    private Bitmap toSoftwareBitmap(ScreenshotResult screenshot) {
        HardwareBuffer buffer = screenshot.getHardwareBuffer();
        try {
            ColorSpace colorSpace = screenshot.getColorSpace();
            Bitmap hardwareBitmap = Bitmap.wrapHardwareBuffer(buffer, colorSpace);
            if (hardwareBitmap == null) {
                return null;
            }
            return hardwareBitmap.copy(Bitmap.Config.ARGB_8888, false);
        } finally {
            buffer.close();
        }
    }

    private void resetSession() {
        episodeGuard.reset();
        sessionId = "";
        sessionAppPackage = "";
        stepOrdinal = 0;
        episodeStartedAtElapsed = 0L;
        inFlight = false;
        forceVisualNextDecision = false;
    }

    private boolean acceptsCallback(long generation) {
        return episodeGuard.accepts(generation, ExecutorPreferences.active(this));
    }

    private void requestSessionStop(String stoppingSessionId) {
        if (stoppingSessionId == null
                || !stoppingSessionId.matches("[A-Za-z0-9_-]{1,200}")) {
            return;
        }
        try {
            JSONObject request = new JSONObject();
            request.put("request_id", UUID.randomUUID().toString());
            apiClient.post(
                    ExecutorPreferences.apiBaseUrl(this),
                    "/v1/navigation/sessions/" + stoppingSessionId + "/stop",
                    request,
                    new NavigationApiClient.Callback() {
                        @Override
                        public void onSuccess(JSONObject response) {
                            // Idempotent server-side cleanup; no new UI work is scheduled.
                        }

                        @Override
                        public void onFailure(String failureClass, String detail) {
                            // Connection failures stay separate from navigation failure.
                        }
                    }
            );
        } catch (JSONException ignored) {
            // UUID and fixed keys cannot normally fail JSON construction.
        }
    }

    private void stop(String message) {
        cancelPending();
        ExecutorPreferences.setActive(this, false);
        releaseScreenAwake();
        publish(message);
    }

    @SuppressWarnings("deprecation")
    private void holdScreenAwake() {
        if (screenWakeLock == null) {
            PowerManager powerManager = (PowerManager) getSystemService(POWER_SERVICE);
            screenWakeLock = powerManager.newWakeLock(
                    PowerManager.SCREEN_DIM_WAKE_LOCK
                            | PowerManager.ACQUIRE_CAUSES_WAKEUP
                            | PowerManager.ON_AFTER_RELEASE,
                    "ExitGuideNavigation:CollectionScreenAwake"
            );
            screenWakeLock.setReferenceCounted(false);
        }
        if (!screenWakeLock.isHeld()) {
            screenWakeLock.acquire();
        }
    }

    private void releaseScreenAwake() {
        if (screenWakeLock != null && screenWakeLock.isHeld()) {
            screenWakeLock.release();
        }
    }

    private void publish(String message) {
        ExecutorPreferences.publishStatus(this, message);
    }

    private static String emptyToNull(String value) {
        return value == null || value.isEmpty() ? null : value;
    }

    private static String text(CharSequence value) {
        return value == null ? "" : value.toString();
    }

    private static final class ActionExecution {
        final boolean succeeded;
        final String observedSignal;
        final String message;

        ActionExecution(boolean succeeded, String observedSignal, String message) {
            this.succeeded = succeeded;
            this.observedSignal = observedSignal;
            this.message = message;
        }
    }
}
