package com.exitguide.navigation.executor;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.ColorSpace;
import android.graphics.Rect;
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
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
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
    private final CollectorContinuationGate continuationGate = new CollectorContinuationGate();
    private final ForegroundAppSessionTracker foregroundAppTracker =
            new ForegroundAppSessionTracker();
    private final VisualScreenAugmenter visualAugmenter = new VisualScreenAugmenter();

    private AccessibilityScreenReader screenReader;
    private NavigationOverlayController overlayController;
    private boolean inFlight;
    private int stepOrdinal;
    private String sessionId = "";
    private String lastActivityName = "";
    private Runnable pendingDecision;
    private PowerManager.WakeLock screenWakeLock;
    private long episodeStartedAtElapsed;
    private long lastRelevantEventElapsed;
    private boolean forceVisualNextDecision;
    private long frameSequence;
    private String collectionRunId = "";
    private String collectionBatchId = "";
    private String collectionStartedAt = "";
    private String lastOperatorSignature = "";
    private int repeatedOperatorCommandCount;

    private final BroadcastReceiver configurationReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String previousSessionId = sessionId;
            resetSession();
            // Configuration changes can replace an active goal while its last
            // callback is still in flight. Close the previous server session
            // before scheduling the replacement so one device never leaves an
            // orphaned active episode behind.
            requestSessionStop(previousSessionId);
            if (ExecutorPreferences.active(ExitGuideAccessibilityService.this)) {
                holdScreenAwake();
                verifyApiAndSchedule();
            } else {
                cancelPending();
                releaseScreenAwake();
            }
        }
    };

    private final BroadcastReceiver diagnosticReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            runInstallationDiagnostic(
                    text(intent.getStringExtra("request_id")),
                    text(intent.getStringExtra("api_base_url"))
            );
        }
    };

    private final BroadcastReceiver statusReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (overlayController != null) {
                overlayController.showStatus(text(intent.getStringExtra("status")));
            }
        }
    };

    private final BroadcastReceiver operatorCommandReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (!ExecutorPreferences.active(ExitGuideAccessibilityService.this)) {
                return;
            }
            continuationGate.reset();
            cancelPending();
            scheduleDecision(0);
        }
    };

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        // Some Compose/WebView-backed account surfaces expose their semantic
        // descendants as non-important views.  UiAutomator can see those
        // descendants, but an AccessibilityService without this fetch flag
        // receives only the empty wrapper node and therefore cannot ground a
        // candidate_id.  Keep the XML declaration and runtime flag in sync so
        // an in-place APK update gets the same behavior after re-binding.
        AccessibilityServiceInfo serviceInfo = getServiceInfo();
        if (serviceInfo != null) {
            serviceInfo.flags |= AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS;
            serviceInfo.flags |= AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
            serviceInfo.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
            setServiceInfo(serviceInfo);
        }
        screenReader = new AccessibilityScreenReader(getResources().getDisplayMetrics());
        overlayController = new NavigationOverlayController(this);
        IntentFilter filter = new IntentFilter(ExecutorPreferences.ACTION_CONFIGURATION_CHANGED);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(configurationReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
            registerReceiver(
                    statusReceiver,
                    new IntentFilter(ExecutorPreferences.ACTION_STATUS_CHANGED),
                    Context.RECEIVER_NOT_EXPORTED
            );
            registerReceiver(
                    diagnosticReceiver,
                    new IntentFilter(ExecutorPreferences.ACTION_DIAGNOSTIC_INTERNAL),
                    Context.RECEIVER_NOT_EXPORTED
            );
            registerReceiver(
                    operatorCommandReceiver,
                    new IntentFilter(ExecutorPreferences.ACTION_OPERATOR_COMMAND_CHANGED),
                    Context.RECEIVER_NOT_EXPORTED
            );
        } else {
            registerReceiver(configurationReceiver, filter);
            registerReceiver(
                    statusReceiver,
                    new IntentFilter(ExecutorPreferences.ACTION_STATUS_CHANGED)
            );
            registerReceiver(
                    diagnosticReceiver,
                    new IntentFilter(ExecutorPreferences.ACTION_DIAGNOSTIC_INTERNAL)
            );
            registerReceiver(
                    operatorCommandReceiver,
                    new IntentFilter(ExecutorPreferences.ACTION_OPERATOR_COMMAND_CHANGED)
            );
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
        if (continuationGate.isWaitingForUser()) {
            resumeIfUserChangedScreen();
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
        AccessibilityNodeInfo activeRoot = activeRoot();
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
        try {
            unregisterReceiver(diagnosticReceiver);
        } catch (IllegalArgumentException ignored) {
            // Service startup did not finish.
        }
        try {
            unregisterReceiver(statusReceiver);
        } catch (IllegalArgumentException ignored) {
            // Service startup did not finish.
        }
        try {
            unregisterReceiver(operatorCommandReceiver);
        } catch (IllegalArgumentException ignored) {
            // Service startup did not finish.
        }
        if (overlayController != null) {
            overlayController.close();
            overlayController = null;
        }
        visualAugmenter.close();
        apiClient.close();
        super.onDestroy();
    }

    private void runInstallationDiagnostic(String requestId, String requestedApiBaseUrl) {
        String safeRequestId = requestId.isEmpty() ? UUID.randomUUID().toString() : requestId;
        publish("현재 화면을 분석하는 중입니다.");
        AccessibilityScreenReader.ScreenSnapshot snapshot = currentSnapshot();
        int nodeCount = 0;
        int candidateCount = 0;
        String packageName = "";
        if (snapshot != null) {
            packageName = snapshot.appPackage;
            if (snapshot.payload.optJSONArray("nodes") != null) {
                nodeCount = snapshot.payload.optJSONArray("nodes").length();
            }
            candidateCount = snapshot.bindings.size();
        }
        Log.i(
                LOG_TAG,
                "diagnostic_snapshot request_id=" + safeRequestId
                        + " package=" + packageName
                        + " nodes=" + nodeCount
                        + " candidates=" + candidateCount
        );

        String apiBaseUrl = requestedApiBaseUrl.isEmpty()
                ? ExecutorPreferences.apiBaseUrl(this)
                : requestedApiBaseUrl;
        apiClient.get(
                apiBaseUrl,
                "/v1/navigation/status",
                new NavigationApiClient.Callback() {
                    @Override
                    public void onSuccess(JSONObject response) {
                        Log.i(
                                LOG_TAG,
                                "diagnostic_api request_id=" + safeRequestId
                                        + " ready=" + response.optBoolean("ready", false)
                                        + " public_prior_enabled=" + (
                                                response.optJSONObject("public_prior") != null
                                                        && response.optJSONObject("public_prior")
                                                        .optBoolean("enabled", false)
                                        )
                        );
                    }

                    @Override
                    public void onFailure(String failureClass, String detail) {
                        Log.w(
                                LOG_TAG,
                                "diagnostic_api request_id=" + safeRequestId
                                        + " ready=false failure_class=" + failureClass
                        );
                    }
                }
        );
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
                            publish("Navigation API가 아직 준비되지 않았습니다. 잠시 후 재확인합니다.");
                            scheduleDecision(2_000);
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
        if (!ExecutorPreferences.active(this)
                || inFlight
                || continuationGate.isWaitingForUser()) {
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
        AccessibilityScreenReader.ScreenSnapshot snapshot = currentSnapshot();
        if (snapshot == null) {
            publish("현재 화면의 접근성 구조를 읽지 못했습니다. 잠시 후 다시 관찰합니다.");
            scheduleDecision(1_000);
            return;
        }
        ForegroundAppSessionTracker.Observation appObservation =
                foregroundAppTracker.observe(snapshot.appPackage);
        if (appObservation.waitForAppChange) {
            awaitForegroundAppChange(snapshot);
            return;
        }
        if (appObservation.startsNewSession) {
            startNewAppSession();
        }
        if (episodeStartedAtElapsed == 0L) {
            episodeStartedAtElapsed = SystemClock.elapsedRealtime();
        }
        ensureCollectionRun();
        if (stepOrdinal >= MAX_ACTIONS) {
            pauseEpisodeAtStepLimit(snapshot);
            return;
        }
        if (SystemClock.elapsedRealtime() - episodeStartedAtElapsed >= MAX_EPISODE_DURATION_MS) {
            rolloverEpisode("10분 탐색 기록을 저장했습니다.");
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
        if (ExecutorPreferences.codexOperatorMode(this)) {
            handleCodexOperatorSnapshot(snapshot, appObservation);
            return;
        }
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
                awaitUserScreenChange(
                        snapshot,
                        "시각 판단이 어려운 화면입니다. 직접 조작해 화면을 바꾸면 자동 재개합니다."
                );
                return;
            }
            postDecision(
                    snapshot,
                    emptyToNull(dataUrl),
                    visualReasoningRequired,
                    appObservation,
                    generation,
                    null
            );
        });
    }

    private void handleCodexOperatorSnapshot(
            AccessibilityScreenReader.ScreenSnapshot snapshot,
            ForegroundAppSessionTracker.Observation appObservation
    ) {
        try {
            LatestScreenStore.write(
                    this,
                    snapshot,
                    ExecutorPreferences.goal(this),
                    packageVersion(appObservation.currentAppPackage),
                    sessionId,
                    stepOrdinal
            );
        } catch (IOException | JSONException error) {
            publish("현재 화면 기록 실패: " + error.getMessage());
            scheduleDecision(1_000);
            return;
        }
        ExecutorPreferences.OperatorCommand command =
                ExecutorPreferences.pendingOperatorCommand(this);
        if (command == null) {
            publish("화면과 후보를 기록했습니다. Codex 선택을 기다립니다.");
            return;
        }
        if (!snapshot.screenFingerprint.equals(command.expectedScreenFingerprint)) {
            ExecutorPreferences.clearOperatorCommand(this);
            publish("화면이 바뀌어 오래된 Codex 명령을 폐기했습니다.");
            return;
        }
        if ("click".equals(command.actionName)
                && !snapshot.bindings.containsKey(command.candidateId)) {
            ExecutorPreferences.clearOperatorCommand(this);
            publish("현재 화면에 없는 후보를 가리킨 Codex 명령을 폐기했습니다.");
            return;
        }
        String operatorSignature = snapshot.screenFingerprint
                + "|" + command.actionName
                + "|" + command.candidateId
                + "|" + command.direction;
        if (operatorSignature.equals(lastOperatorSignature)) {
            repeatedOperatorCommandCount++;
        } else {
            lastOperatorSignature = operatorSignature;
            repeatedOperatorCommandCount = 1;
        }
        if (repeatedOperatorCommandCount >= 3) {
            ExecutorPreferences.clearOperatorCommand(this);
            String previousSessionId = sessionId;
            resetEpisodeForContinuation();
            requestSessionStop(
                    previousSessionId,
                    "loop_detected",
                    "same_screen_operator_action_repeated"
            );
            publish("같은 화면에서 같은 행동이 반복되어 세션만 닫았습니다. 다른 선택을 기다립니다.");
            scheduleDecision(300);
            return;
        }
        long generation = episodeGuard.current();
        inFlight = true;
        ExecutorPreferences.clearOperatorCommand(this);
        prepareVisualContext(snapshot, false, (dataUrl, visualReasoningRequired) -> {
            if (!acceptsCallback(generation)) {
                return;
            }
            postDecision(
                    snapshot,
                    emptyToNull(dataUrl),
                    visualReasoningRequired,
                    appObservation,
                    generation,
                    command
            );
        });
    }

    private void postDecision(
            AccessibilityScreenReader.ScreenSnapshot snapshot,
            String screenshotDataUrl,
            boolean visualReasoningRequired,
            ForegroundAppSessionTracker.Observation appObservation,
            long generation,
            ExecutorPreferences.OperatorCommand operatorCommand
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
            request.put("app_package", appObservation.currentAppPackage);
            request.put("origin_app_package", appObservation.originAppPackage);
            request.put("current_app_package", appObservation.currentAppPackage);
            request.put("previous_app_package", appObservation.previousAppPackage);
            request.put("transition_reason", appObservation.transitionReason);
            request.put("app_version", packageVersion(appObservation.currentAppPackage));
            request.put("locale", Locale.getDefault().toLanguageTag());
            request.put("goal_text", ExecutorPreferences.goal(this));
            request.put("step_ordinal", stepOrdinal);
            request.put("visual_reasoning_required", visualReasoningRequired);
            request.put(
                    "collection_run",
                    CollectionRunMetadata.build(
                            this,
                            collectionRunId,
                            collectionBatchId,
                            collectionStartedAt
                    )
            );
            request.put("task_context", CollectionRunMetadata.taskContext(this));
            if (operatorCommand != null) {
                request.put("operator_action", operatorAction(operatorCommand));
                request.put("operator_source", "codex");
                request.put("operator_command_id", operatorCommand.commandId);
                request.put("operator_reason_codes", reasonCodes(operatorCommand.reasonCodesCsv));
                request.put("operator_reason_text", operatorCommand.reasonText);
                request.put("operator_review_status", operatorCommand.reviewStatus);
            }
            if (screenshotDataUrl != null) {
                request.put("screenshot_data_url", screenshotDataUrl);
            }
            request.put("screen", snapshot.payload);
            publish(operatorCommand == null
                    ? "다음 안전 행동을 판단하는 중입니다."
                    : "Codex 선택을 안전 검사하고 기록하는 중입니다.");
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
                            if (isDatasetAccessDenied(failureClass, detail)) {
                                foregroundAppTracker.markCurrentAppUnsupported();
                                awaitForegroundAppChange(snapshot);
                                return;
                            }
                            publish("판단 요청 실패(" + failureClass + "). 잠시 후 다시 시도합니다.");
                            scheduleDecision(2_000);
                        }
                    }
            );
        } catch (JSONException error) {
            inFlight = false;
            stop("판단 요청을 만들 수 없습니다: " + error.getMessage());
        }
    }

    private static JSONObject operatorAction(
            ExecutorPreferences.OperatorCommand command
    ) throws JSONException {
        JSONObject action = new JSONObject();
        action.put("name", command.actionName);
        if (!command.candidateId.isEmpty()) {
            action.put("candidate_id", command.candidateId);
        }
        if (!command.direction.isEmpty()) {
            action.put("direction", command.direction);
        }
        return action;
    }

    private static JSONArray reasonCodes(String csv) {
        JSONArray values = new JSONArray();
        for (String item : csv.split(",")) {
            String value = item.trim();
            if (!value.isEmpty()) {
                values.put(value);
            }
        }
        return values;
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
                    new ActionExecution(false, "blocked", "허용되지 않은 행동을 차단했습니다."),
                    true,
                    "허용되지 않은 행동을 차단했습니다: " + actionName,
                    "safe_user_handoff",
                    "blocked_by_executor"
            );
            return;
        }
        publishDecisionContext(response, action, beforeSnapshot);
        if (response.optBoolean("visual_reobserve_required", false)) {
            if (!"wait_and_observe".equals(actionName)) {
                observeDecision(
                        decisionId,
                        beforeSnapshot,
                        beforeScreenshot,
                        generation,
                        new ActionExecution(
                                false,
                                "blocked",
                                "VLM 재관찰 요청과 실행 행동이 충돌했습니다."
                        ),
                        true,
                        "VLM 재관찰 요청이 클릭 행동과 함께 반환되어 안전하게 차단했습니다.",
                        "safe_user_handoff",
                        "blocked_by_executor"
                );
                return;
            }
            forceVisualNextDecision = true;
            publish("후보가 모호하여 candidate_id 오버레이로 다시 관찰합니다: "
                    + response.optString("visual_reobserve_reason", "visual_context_required"));
        }
        if ("stop_for_user".equals(actionName)) {
            publish("자동 행동을 잠시 멈춥니다. 직접 조작해 화면을 바꾸면 탐색을 재개합니다.");
            observeDecision(
                    decisionId,
                    beforeSnapshot,
                    beforeScreenshot,
                    generation,
                    new ActionExecution(false, "blocked", "사용자 확인이 필요합니다."),
                    true,
                    "현재 화면은 사용자 조작이 필요합니다.",
                    "safe_user_handoff",
                    "confirmation_required"
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
                execution,
                false,
                "",
                "",
                ""
        );
    }

    private ActionExecution execute(
            JSONObject action,
            AccessibilityScreenReader.ScreenSnapshot snapshot
    ) {
        long startedAt = SystemClock.elapsedRealtime();
        String name = action.optString("name", "");
        switch (name) {
            case "click":
                return clickCandidate(
                        action.optString("candidate_id", ""), snapshot, startedAt
                );
            case "scroll":
                return scroll(action.optString("direction", "down"), startedAt);
            case "back":
                return new ActionExecution(
                        performGlobalAction(GLOBAL_ACTION_BACK),
                        "none",
                        "뒤로가기를 실행했습니다.",
                        actionPayload("back", "", ""),
                        "system_global_action",
                        startedAt,
                        SystemClock.elapsedRealtime(),
                        ""
                );
            case "wait_and_observe":
                return new ActionExecution(
                        true,
                        "none",
                        "화면 변화를 기다립니다.",
                        actionPayload("wait_and_observe", "", ""),
                        "wait",
                        startedAt,
                        SystemClock.elapsedRealtime(),
                        ""
                );
            default:
                return new ActionExecution(false, "blocked", "허용되지 않은 행동을 차단했습니다.");
        }
    }

    private ActionExecution clickCandidate(
            String candidateId,
            AccessibilityScreenReader.ScreenSnapshot snapshot,
            long startedAt
    ) {
        AccessibilityScreenReader.CandidateBinding binding = snapshot.bindings.get(candidateId);
        if (binding == null) {
            return new ActionExecution(false, "blocked", "현재 화면에 없는 후보 ID를 차단했습니다.");
        }
        if (!"low".equals(binding.riskLevel)) {
            return new ActionExecution(false, "blocked", "위험하거나 입력 상태를 바꾸는 후보를 차단했습니다.");
        }
        if (NavigationSafetyPolicy.isStateChangingActionLabel(binding.label)) {
            return new ActionExecution(false, "blocked", "상태 변경 행동은 사용자가 직접 수행해야 합니다.");
        }
        AccessibilityNodeInfo root = activeRoot();
        if (root == null) {
            return new ActionExecution(false, "blocked", "클릭 직전 현재 화면을 다시 읽지 못했습니다.");
        }
        AccessibilityNodeInfo node = null;
        try {
            node = screenReader.resolve(root, binding);
            if (node == null || !node.isVisibleToUser() || !node.isEnabled() || !node.isClickable()) {
                return new ActionExecution(false, "blocked", "후보가 바뀌어 클릭을 취소했습니다.");
            }
            if (NavigationSafetyPolicy.isStateChangingActionLabel(binding.label)
                    || !"low".equals(NavigationSafetyPolicy.riskLevel(node, binding.semanticText))) {
                return new ActionExecution(false, "blocked", "클릭 직전 안전 재검사에서 후보를 차단했습니다.");
            }
            Rect clickBounds = new Rect();
            node.getBoundsInScreen(clickBounds);
            boolean succeeded = node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            if (succeeded && overlayController != null) {
                overlayController.showTap(clickBounds);
            }
            Log.i(
                    LOG_TAG,
                    "action_execution name=click candidate_id=" + candidateId
                            + " executor_action_succeeded=" + succeeded
            );
            return new ActionExecution(
                    succeeded,
                    succeeded ? "none" : "blocked",
                    succeeded ? "후보 ID를 안전하게 클릭했습니다." : "Accessibility 클릭이 거절되었습니다.",
                    actionPayload("click", candidateId, ""),
                    "accessibility_action",
                    startedAt,
                    SystemClock.elapsedRealtime(),
                    succeeded ? "" : "accessibility_action_rejected"
            );
        } finally {
            if (node != null && !binding.path.isEmpty()) {
                node.recycle();
            }
            root.recycle();
        }
    }

    private ActionExecution scroll(String direction, long startedAt) {
        AccessibilityNodeInfo root = activeRoot();
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
                    succeeded ? "Accessibility 스크롤을 실행했습니다." : "Accessibility 스크롤이 거절되었습니다.",
                    actionPayload("scroll", "", direction),
                    "accessibility_action",
                    startedAt,
                    SystemClock.elapsedRealtime(),
                    succeeded ? "" : "accessibility_action_rejected"
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
            ActionExecution execution,
            boolean stopAfterObserve,
            String stopMessage,
            String terminalReason,
            String handoffReason
    ) {
        if (!acceptsCallback(generation)) {
            return;
        }
        AccessibilityScreenReader.ScreenSnapshot afterSnapshot = currentSnapshot();
        if (afterSnapshot == null) {
            postUnobservedOutcome(
                    decisionId,
                    generation,
                    execution,
                    stopAfterObserve,
                    stopMessage,
                    terminalReason,
                    handoffReason
            );
            return;
        }
        String detectedSignal = ObservationSignalDetector.detect(
                execution.observedSignal,
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
                "post_action_observation executor_action_succeeded=" + execution.succeeded
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
                request.put("execution_succeeded", execution.succeeded);
                request.put(
                        "execution_report",
                        execution.report(
                                Math.max(0L, SystemClock.elapsedRealtime() - execution.finishedAt),
                                "ui_quiet_window",
                                afterSnapshot.appPackage
                        )
                );
                if (!terminalReason.isEmpty()) {
                    request.put("terminal_reason", terminalReason);
                    request.put("handoff_reason", handoffReason);
                }
                if (beforeScreenshot != null) {
                    request.put("before_screenshot_data_url", beforeScreenshot);
                }
                if (!afterScreenshot.isEmpty()) {
                    request.put("after_screenshot_data_url", afterScreenshot);
                }
                request.put("next_screen", afterSnapshot.payload);
                postObservation(
                        request,
                        generation,
                        stopAfterObserve,
                        stopMessage,
                        afterSnapshot
                );
            } catch (JSONException error) {
                inFlight = false;
                stop("관찰 요청을 만들 수 없습니다: " + error.getMessage());
            }
        });
    }

    private void postUnobservedOutcome(
            String decisionId,
            long generation,
            ActionExecution execution,
            boolean stopAfterObserve,
            String stopMessage,
            String terminalReason,
            String handoffReason
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
            request.put("execution_succeeded", execution.succeeded);
            request.put(
                    "execution_report",
                    execution.report(null, "screen_unavailable", "")
            );
            request.put(
                    "terminal_reason",
                    terminalReason.isEmpty() ? "device_disconnected" : terminalReason
            );
            if (!handoffReason.isEmpty()) {
                request.put("handoff_reason", handoffReason);
            }
            postObservation(request, generation, stopAfterObserve, stopMessage, null);
        } catch (JSONException error) {
            inFlight = false;
            stop("기기 관찰 오류를 기록하지 못했습니다.");
        }
    }

    private void postObservation(
            JSONObject request,
            long generation,
            boolean stopAfterObserve,
            String stopMessage,
            AccessibilityScreenReader.ScreenSnapshot continuationBaseline
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
                            awaitUserScreenChange(continuationBaseline, terminalMessage);
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
                        awaitUserScreenChange(
                                continuationBaseline,
                                "관찰 전송 실패(" + failureClass
                                        + "). 직접 조작 후 새 실행으로 다시 이어갑니다."
                        );
                    }
                }
        );
    }

    private AccessibilityScreenReader.ScreenSnapshot currentSnapshot() {
        AccessibilityNodeInfo root = activeRoot();
        if (root == null || screenReader == null) {
            return null;
        }
        try {
            AccessibilityScreenReader.ScreenSnapshot snapshot = screenReader.read(
                    root, lastActivityName, hasMultipleApplicationWindows()
            );
            snapshot.payload.put("frame_sequence_no", frameSequence++);
            return snapshot;
        } catch (JSONException error) {
            publish("접근성 화면 구조화 실패: " + error.getMessage());
            return null;
        } finally {
            root.recycle();
        }
    }

    private AccessibilityNodeInfo activeRoot() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            return getRootInActiveWindow(
                    AccessibilityNodeInfo.FLAG_PREFETCH_DESCENDANTS_BREADTH_FIRST
                            | AccessibilityNodeInfo.FLAG_PREFETCH_UNINTERRUPTIBLE
            );
        }
        return getRootInActiveWindow();
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
        // Accessibility remains the fast path only when it actually provides
        // a clear, grounded candidate set.  Sparse wrappers, missing labels,
        // duplicate labels and visual surfaces must be sent to the selective
        // screenshot/OCR/VLM path before the API can mistake "no candidates"
        // for a navigation failure or recover with back().
        boolean accessibilityNeedsVisualReasoning = screenReader == null
                || screenReader.needsVisualReasoning(snapshot);
        boolean visualReasoningRequired = shouldRequestVisualReasoning(
                forceCapture,
                accessibilityNeedsVisualReasoning
        );
        if (!visualReasoningRequired) {
            Log.i(LOG_TAG, "visual_context skipped reason=accessibility_clear");
            VisualScreenAugmenter.redactSnapshotInPlace(snapshot);
            callback.onReady("", false);
            return;
        }
        if (overlayController != null) {
            overlayController.hideForCapture();
        }
        handler.postDelayed(
                () -> takeVisualScreenshot(snapshot, visualReasoningRequired, callback),
                NavigationOverlayController.CAPTURE_HIDE_DELAY_MS
        );
    }

    private void takeVisualScreenshot(
            AccessibilityScreenReader.ScreenSnapshot snapshot,
            boolean visualReasoningRequired,
            VisualContextCallback callback
    ) {
        try {
            takeScreenshot(
                    Display.DEFAULT_DISPLAY,
                    getMainExecutor(),
                    new TakeScreenshotCallback() {
                        @Override
                        public void onSuccess(ScreenshotResult screenshot) {
                            restoreOverlayAfterCapture();
                            Bitmap bitmap = toSoftwareBitmap(screenshot);
                            if (bitmap == null) {
                                callback.onReady("", visualReasoningRequired);
                                return;
                            }
                            visualAugmenter.augment(bitmap, snapshot, (dataUrl, mergedOcrLines) -> {
                                bitmap.recycle();
                                VisualScreenAugmenter.redactSnapshotInPlace(snapshot);
                                put(
                                        snapshot.payload,
                                        "screenshot_tree_delta_ms",
                                        Math.max(
                                                0L,
                                                SystemClock.elapsedRealtime()
                                                        - snapshot.payload.optLong(
                                                                "captured_device_monotonic_ms",
                                                                SystemClock.elapsedRealtime()
                                                        )
                                        )
                                );
                                addCaptureCapability(snapshot.payload, "screenshot");
                                addCaptureCapability(snapshot.payload, "ocr");
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
                            restoreOverlayAfterCapture();
                            Log.w(LOG_TAG, "screenshot failed code=" + errorCode);
                            VisualScreenAugmenter.redactSnapshotInPlace(snapshot);
                            addMissingPart(snapshot.payload, "screenshot_unavailable");
                            callback.onReady("", visualReasoningRequired);
                        }
                    }
            );
        } catch (IllegalStateException | SecurityException error) {
            restoreOverlayAfterCapture();
            Log.w(LOG_TAG, "screenshot unavailable=" + error.getClass().getSimpleName());
            VisualScreenAugmenter.redactSnapshotInPlace(snapshot);
            addMissingPart(snapshot.payload, "screenshot_unavailable");
            callback.onReady("", visualReasoningRequired);
        }
    }

    private void restoreOverlayAfterCapture() {
        if (overlayController != null) {
            overlayController.restoreAfterCapture();
        }
    }

    private static void addCaptureCapability(JSONObject screen, String capability) {
        org.json.JSONArray capabilities = screen.optJSONArray("capture_capabilities");
        if (capabilities == null) {
            capabilities = new org.json.JSONArray();
            put(screen, "capture_capabilities", capabilities);
        }
        for (int index = 0; index < capabilities.length(); index++) {
            if (capability.equals(capabilities.optString(index))) {
                return;
            }
        }
        capabilities.put(capability);
    }

    private static void addMissingPart(JSONObject screen, String missingPart) {
        org.json.JSONArray missing = screen.optJSONArray("missing_parts");
        if (missing == null) {
            missing = new org.json.JSONArray();
            put(screen, "missing_parts", missing);
        }
        missing.put(missingPart);
    }

    private static void put(JSONObject target, String key, Object value) {
        try {
            target.put(key, value);
        } catch (JSONException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    static boolean shouldRequestVisualReasoning(
            boolean forceCapture,
            boolean accessibilityNeedsVisualReasoning
    ) {
        return forceCapture || accessibilityNeedsVisualReasoning;
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
        resetEpisodeForContinuation();
        foregroundAppTracker.reset();
        collectionBatchId = "";
    }

    private void ensureCollectionRun() {
        if (!collectionRunId.isEmpty()) {
            return;
        }
        collectionRunId = CollectionRunMetadata.newRunId();
        if (collectionBatchId.isEmpty()) {
            collectionBatchId = collectionRunId;
        }
        collectionStartedAt = CollectionRunMetadata.now();
    }

    private void awaitUserScreenChange(
            AccessibilityScreenReader.ScreenSnapshot baseline,
            String message
    ) {
        inFlight = false;
        cancelPending();
        requestSessionStop(sessionId);
        continuationGate.awaitUserScreenChange(
                baseline == null ? "" : baseline.appPackage,
                baseline == null ? "" : baseline.screenFingerprint
        );
        releaseScreenAwake();
        publish(message + " 화면이나 앱이 바뀌면 자동으로 다시 시작합니다.");
        resumeIfUserChangedScreen();
    }

    private void rolloverEpisode(String message) {
        inFlight = false;
        cancelPending();
        String previousSessionId = sessionId;
        resetEpisodeForContinuation();
        requestSessionStop(previousSessionId);
        holdScreenAwake();
        publish(message + " 새 세션으로 자동 탐색을 계속합니다.");
        scheduleDecision(300);
    }

    private void pauseEpisodeAtStepLimit(
            AccessibilityScreenReader.ScreenSnapshot baseline
    ) {
        inFlight = false;
        cancelPending();
        requestSessionStop(
                sessionId,
                "step_limit",
                "maximum_action_count_reached"
        );
        continuationGate.awaitUserScreenChange(
                baseline == null ? "" : baseline.appPackage,
                baseline == null ? "" : baseline.screenFingerprint
        );
        releaseScreenAwake();
        publish("15개 행동 한도에 도달해 자동 탐색을 멈췄습니다. "
                + "화면이나 앱이 바뀌면 새 세션으로 다시 시작합니다.");
    }

    private void resumeIfUserChangedScreen() {
        if (!continuationGate.isWaitingForUser()) {
            return;
        }
        AccessibilityScreenReader.ScreenSnapshot snapshot = currentSnapshot();
        if (snapshot == null || !continuationGate.consumeIfScreenChanged(
                snapshot.appPackage,
                snapshot.screenFingerprint
        )) {
            return;
        }
        resetEpisodeForUserResume();
        holdScreenAwake();
        publish("화면 변화를 확인했습니다. 안전 탐색을 자동 재개합니다.");
        scheduleDecision(300);
    }

    private void resetEpisodeForUserResume() {
        resetEpisodeForContinuation();
    }

    private void startNewAppSession() {
        String previousSessionId = sessionId;
        resetEpisodeForContinuation();
        requestSessionStop(previousSessionId);
        publish("현재 앱이 바뀌어 새 수집 세션으로 이어갑니다.");
    }

    private void resetEpisodeForContinuation() {
        episodeGuard.reset();
        sessionId = "";
        stepOrdinal = 0;
        episodeStartedAtElapsed = 0L;
        inFlight = false;
        continuationGate.reset();
        forceVisualNextDecision = false;
        frameSequence = 0L;
        collectionRunId = "";
        collectionStartedAt = "";
        lastOperatorSignature = "";
        repeatedOperatorCommandCount = 0;
    }

    private void awaitForegroundAppChange(AccessibilityScreenReader.ScreenSnapshot baseline) {
        inFlight = false;
        cancelPending();
        requestSessionStop(sessionId);
        continuationGate.awaitAppChange(baseline == null ? "" : baseline.appPackage);
        releaseScreenAwake();
        publish("현재 화면은 수집하지 않습니다. 다른 앱으로 전환하면 자동으로 다시 시작합니다.");
        resumeIfUserChangedScreen();
    }

    private static boolean isDatasetAccessDenied(String failureClass, String detail) {
        return "http_error".equals(failureClass)
                && detail != null
                && detail.startsWith("HTTP 403:")
                && (detail.contains("app_package_not_assigned_to_dataset_split")
                || detail.contains("locked_holdout_access_denied"));
    }

    private void publishDecisionContext(
            JSONObject response,
            JSONObject action,
            AccessibilityScreenReader.ScreenSnapshot snapshot
    ) {
        JSONObject context = response.optJSONObject("safety_context");
        if (context == null) {
            return;
        }
        String actionName = action.optString("name", "");
        String actionLabel = actionName;
        if ("click".equals(actionName)) {
            AccessibilityScreenReader.CandidateBinding binding = snapshot.bindings.get(
                    action.optString("candidate_id", "")
            );
            actionLabel = binding == null || binding.label.isEmpty() ? "항목 선택" : binding.label;
        } else if ("scroll".equals(actionName)) {
            actionLabel = "up".equals(action.optString("direction", "down"))
                    ? "위로 스크롤" : "아래로 스크롤";
        } else if ("back".equals(actionName)) {
            actionLabel = "뒤로 이동";
        } else if ("wait_and_observe".equals(actionName)) {
            actionLabel = "화면 변화 대기";
        } else if ("stop_for_user".equals(actionName)) {
            actionLabel = "사용자에게 넘기기";
        }
        String stage = humanizeProcedureStage(context.optString("procedure_stage", "unknown"));
        String effect = humanizeEffect(context.optString("effect_class", "unknown"));
        String safety = context.optBoolean("boundary", false)
                ? "사용자 확인" : "자동 진행";
        publish("다음 행동: " + compactStatusPart(actionLabel)
                + " | 단계: " + stage
                + " | 예상: " + effect
                + " | " + safety);
    }

    private static String humanizeProcedureStage(String value) {
        switch (value) {
            case "terminal_boundary":
                return "최종 확인 단계";
            case "review_before_commit":
                return "최종 실행 전 검토";
            case "goal_disambiguation":
                return "목적 확인";
            case "selective_recovery":
                return "경로 복구";
            case "unknown":
            case "":
                return "화면 판단";
            default:
                return compactStatusPart(value.replace('_', ' '));
        }
    }

    private static String humanizeEffect(String value) {
        switch (value) {
            case "navigate_only":
                return "화면만 이동";
            case "observe_only":
                return "변화 관찰";
            case "user_handoff":
                return "사용자 조작 필요";
            case "goal_reached":
                return "목적 달성";
            case "automatic_recovery":
                return "자동 경로 복구";
            default:
                return "결과 확인 필요";
        }
    }

    private static String compactStatusPart(String value) {
        String safe = value == null ? "" : value.trim().replaceAll("\\s+", " ");
        return safe.length() <= 45 ? safe : safe.substring(0, 42) + "...";
    }

    private boolean acceptsCallback(long generation) {
        return episodeGuard.accepts(generation, ExecutorPreferences.active(this));
    }

    private void requestSessionStop(String stoppingSessionId) {
        requestSessionStop(stoppingSessionId, "manual_stop", "");
    }

    private void requestSessionStop(
            String stoppingSessionId,
            String terminalReason,
            String handoffReason
    ) {
        if (stoppingSessionId == null
                || !stoppingSessionId.matches("[A-Za-z0-9_-]{1,200}")) {
            return;
        }
        try {
            JSONObject request = new JSONObject();
            request.put("request_id", UUID.randomUUID().toString());
            request.put("terminal_reason", terminalReason);
            if (handoffReason != null && !handoffReason.isEmpty()) {
                request.put("handoff_reason", handoffReason);
            }
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
        if (overlayController != null) {
            overlayController.showStatus(message);
        }
    }

    private static String emptyToNull(String value) {
        return value == null || value.isEmpty() ? null : value;
    }

    private static String text(CharSequence value) {
        return value == null ? "" : value.toString();
    }

    private static JSONObject actionPayload(String name, String candidateId, String direction) {
        JSONObject payload = new JSONObject();
        put(payload, "name", name);
        put(payload, "candidate_id", candidateId.isEmpty() ? JSONObject.NULL : candidateId);
        put(payload, "direction", direction.isEmpty() ? JSONObject.NULL : direction);
        return payload;
    }

    private static final class ActionExecution {
        final boolean succeeded;
        final String observedSignal;
        final String message;
        final JSONObject actualAction;
        final String executorMethod;
        final long startedAt;
        final long finishedAt;
        final String failureCode;

        ActionExecution(boolean succeeded, String observedSignal, String message) {
            this(
                    succeeded,
                    observedSignal,
                    message,
                    null,
                    "not_executed",
                    SystemClock.elapsedRealtime(),
                    SystemClock.elapsedRealtime(),
                    succeeded ? "" : observedSignal
            );
        }

        ActionExecution(
                boolean succeeded,
                String observedSignal,
                String message,
                JSONObject actualAction,
                String executorMethod,
                long startedAt,
                long finishedAt,
                String failureCode
        ) {
            this.succeeded = succeeded;
            this.observedSignal = observedSignal;
            this.message = message;
            this.actualAction = actualAction;
            this.executorMethod = executorMethod;
            this.startedAt = startedAt;
            this.finishedAt = finishedAt;
            this.failureCode = failureCode;
        }

        JSONObject report(
                Long settleDurationMs,
                String settleReason,
                String externalPackage
        ) throws JSONException {
            JSONObject report = new JSONObject();
            report.put(
                    "actual_action",
                    actualAction == null ? JSONObject.NULL : actualAction
            );
            report.put("executor_method", executorMethod);
            report.put("attempt_no", 1);
            report.put("execution_started_device_monotonic_ms", startedAt);
            report.put("execution_finished_device_monotonic_ms", finishedAt);
            report.put("failure_code", failureCode);
            report.put(
                    "settle_duration_ms",
                    settleDurationMs == null ? JSONObject.NULL : settleDurationMs
            );
            report.put("settle_reason", settleReason);
            report.put("external_package", externalPackage);
            report.put("human_intervention", false);
            return report;
        }
    }
}
