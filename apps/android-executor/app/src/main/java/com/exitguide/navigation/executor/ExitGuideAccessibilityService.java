package com.exitguide.navigation.executor;

import android.accessibilityservice.AccessibilityService;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Bitmap;
import android.graphics.ColorSpace;
import android.hardware.HardwareBuffer;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.util.Base64;
import java.util.Locale;
import java.util.UUID;

public final class ExitGuideAccessibilityService extends AccessibilityService {
    private interface ScreenshotCallback {
        void onCaptured(String dataUrl);
    }

    private static final long EVENT_DEBOUNCE_MS = 700;
    private static final long OBSERVATION_DELAY_MS = 1_200;
    private static final int MAX_ACTIONS = 15;
    private static final long MAX_EPISODE_DURATION_MS = 10 * 60 * 1_000L;
    private static final int MAX_SCREENSHOT_EDGE = 900;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final NavigationApiClient apiClient = new NavigationApiClient();

    private AccessibilityScreenReader screenReader;
    private boolean inFlight;
    private int stepOrdinal;
    private String sessionId = "";
    private String sessionAppPackage = "";
    private String lastActivityName = "";
    private Runnable pendingDecision;
    private PowerManager.WakeLock screenWakeLock;
    private long episodeStartedAtElapsed;

    private final BroadcastReceiver configurationReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            resetSession();
            if (ExecutorPreferences.active(ExitGuideAccessibilityService.this)) {
                holdScreenAwake();
                verifyApiAndSchedule();
            } else {
                cancelPending();
                releaseScreenAwake();
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
        if (event == null || !ExecutorPreferences.active(this) || inFlight) {
            return;
        }
        String packageName = text(event.getPackageName());
        if (getPackageName().equals(packageName)) {
            return;
        }
        lastActivityName = text(event.getClassName());
        scheduleDecision(EVENT_DEBOUNCE_MS);
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
        apiClient.close();
        super.onDestroy();
    }

    private void verifyApiAndSchedule() {
        holdScreenAwake();
        publish("Navigation API 상태를 확인하는 중입니다.");
        apiClient.get(
                ExecutorPreferences.apiBaseUrl(this),
                "/v1/navigation/status",
                new NavigationApiClient.Callback() {
                    @Override
                    public void onSuccess(JSONObject response) {
                        if (!response.optBoolean("ready", false)) {
                            stop("Navigation API가 준비되지 않았습니다.");
                            return;
                        }
                        publish("Navigation API 연결됨: " + response.optString("serving_mode", "unknown"));
                        scheduleDecision(300);
                    }

                    @Override
                    public void onFailure(String failureClass, String detail) {
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
        cancelPending();
        pendingDecision = this::requestDecision;
        handler.postDelayed(pendingDecision, delayMs);
    }

    private void cancelPending() {
        if (pendingDecision != null) {
            handler.removeCallbacks(pendingDecision);
            pendingDecision = null;
        }
    }

    private void requestDecision() {
        pendingDecision = null;
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
        inFlight = true;
        captureScreenshot(dataUrl -> postDecision(snapshot, emptyToNull(dataUrl)));
    }

    private void postDecision(
            AccessibilityScreenReader.ScreenSnapshot snapshot,
            String screenshotDataUrl
    ) {
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
            request.put("locale", Locale.getDefault().toLanguageTag());
            request.put("goal_text", ExecutorPreferences.goal(this));
            request.put("step_ordinal", stepOrdinal);
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
                            handleDecision(response, snapshot, screenshotDataUrl);
                        }

                        @Override
                        public void onFailure(String failureClass, String detail) {
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
            String beforeScreenshot
    ) {
        sessionId = response.optString("session_id", sessionId);
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
                    false,
                    "blocked",
                    true,
                    "허용되지 않은 행동을 차단했습니다: " + actionName
            );
            return;
        }
        if ("stop_for_user".equals(actionName)) {
            observeDecision(
                    decisionId,
                    beforeSnapshot,
                    beforeScreenshot,
                    false,
                    "blocked",
                    true,
                    "목적지 또는 위험한 최종 행동 앞에서 멈췄습니다. 사용자가 직접 확인하세요."
            );
            return;
        }

        ActionExecution execution = execute(action, beforeSnapshot);
        publish(execution.message);
        handler.postDelayed(
                () -> observeDecision(
                        decisionId,
                        beforeSnapshot,
                        beforeScreenshot,
                        execution.succeeded,
                        execution.observedSignal,
                        false,
                        ""
                ),
                "wait_and_observe".equals(actionName) ? 1_600 : OBSERVATION_DELAY_MS
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
        AccessibilityNodeInfo node = screenReader.resolve(root, binding);
        if (node == null || !node.isVisibleToUser() || !node.isEnabled() || !node.isClickable()) {
            return new ActionExecution(false, "blocked", "후보가 바뀌어 클릭을 취소했습니다.");
        }
        if (!"low".equals(NavigationSafetyPolicy.riskLevel(node, binding.semanticText))) {
            return new ActionExecution(false, "blocked", "클릭 직전 안전 재검사에서 후보를 차단했습니다.");
        }
        boolean succeeded = node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        return new ActionExecution(
                succeeded,
                succeeded ? "none" : "blocked",
                succeeded ? "후보 ID를 안전하게 클릭했습니다." : "Accessibility 클릭이 거절되었습니다."
        );
    }

    private ActionExecution scroll(String direction) {
        AccessibilityNodeInfo scrollable = findScrollable(getRootInActiveWindow());
        if (scrollable == null) {
            return new ActionExecution(false, "blocked", "스크롤 가능한 영역을 찾지 못했습니다.");
        }
        int action = "up".equals(direction)
                ? AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
                : AccessibilityNodeInfo.ACTION_SCROLL_FORWARD;
        boolean succeeded = scrollable.performAction(action);
        return new ActionExecution(
                succeeded,
                succeeded ? "none" : "blocked",
                succeeded ? "Accessibility 스크롤을 실행했습니다." : "Accessibility 스크롤이 거절되었습니다."
        );
    }

    private AccessibilityNodeInfo findScrollable(AccessibilityNodeInfo node) {
        if (node == null) {
            return null;
        }
        if (node.isVisibleToUser() && node.isScrollable()) {
            return node;
        }
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo found = findScrollable(node.getChild(index));
            if (found != null) {
                return found;
            }
        }
        return null;
    }

    private void observeDecision(
            String decisionId,
            AccessibilityScreenReader.ScreenSnapshot beforeSnapshot,
            String beforeScreenshot,
            boolean executionSucceeded,
            String executionSignal,
            boolean stopAfterObserve,
            String stopMessage
    ) {
        AccessibilityScreenReader.ScreenSnapshot afterSnapshot = currentSnapshot();
        if (afterSnapshot == null) {
            postUnobservedOutcome(decisionId, executionSucceeded, stopAfterObserve, stopMessage);
            return;
        }
        String observedSignal = ObservationSignalDetector.detect(
                executionSignal,
                beforeSnapshot.appPackage,
                afterSnapshot.appPackage,
                afterSnapshot.payload.toString()
        );
        captureScreenshot(afterScreenshot -> {
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
                postObservation(request, stopAfterObserve, stopMessage);
            } catch (JSONException error) {
                inFlight = false;
                stop("관찰 요청을 만들 수 없습니다: " + error.getMessage());
            }
        });
    }

    private void postUnobservedOutcome(
            String decisionId,
            boolean executionSucceeded,
            boolean stopAfterObserve,
            String stopMessage
    ) {
        try {
            JSONObject request = new JSONObject();
            request.put("request_id", UUID.randomUUID().toString());
            request.put("decision_id", decisionId);
            request.put("connectivity_status", "device_disconnected");
            request.put("observed_signal", "none");
            request.put("execution_succeeded", executionSucceeded);
            postObservation(request, stopAfterObserve, stopMessage);
        } catch (JSONException error) {
            inFlight = false;
            stop("기기 관찰 오류를 기록하지 못했습니다.");
        }
    }

    private void postObservation(
            JSONObject request,
            boolean stopAfterObserve,
            String stopMessage
    ) {
        apiClient.post(
                ExecutorPreferences.apiBaseUrl(this),
                "/v1/navigation/observe",
                request,
                new NavigationApiClient.Callback() {
                    @Override
                    public void onSuccess(JSONObject response) {
                        inFlight = false;
                        stepOrdinal++;
                        String outcome = response.optString("outcome_type", "unknown");
                        String progress = response.optString("progress_label", "unknown");
                        publish("관찰 결과: " + outcome + " / " + progress);
                        if (stopAfterObserve || "destination_reached".equals(outcome)) {
                            stop(stopMessage.isEmpty()
                                    ? "목적지에 도달했습니다. 최종 행동은 사용자가 직접 수행하세요."
                                    : stopMessage);
                            return;
                        }
                        JSONObject recovery = response.optJSONObject("recovery_action");
                        if (recovery != null) {
                            String recoveryName = recovery.optString("name", "reselect");
                            if ("stop_for_user".equals(recoveryName)) {
                                stop("인증·위험·차단 경계가 감지되어 사용자의 확인이 필요합니다.");
                                return;
                            }
                            publish("복구 필요: " + recoveryName
                                    + ". 다음 판단에서 안전하게 반영합니다.");
                        }
                        scheduleDecision(500);
                    }

                    @Override
                    public void onFailure(String failureClass, String detail) {
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
            return screenReader.read(root, lastActivityName);
        } catch (JSONException error) {
            publish("접근성 화면 구조화 실패: " + error.getMessage());
            return null;
        }
    }

    private void captureScreenshot(ScreenshotCallback callback) {
        try {
            takeScreenshot(
                    Display.DEFAULT_DISPLAY,
                    getMainExecutor(),
                    new TakeScreenshotCallback() {
                        @Override
                        public void onSuccess(ScreenshotResult screenshot) {
                            callback.onCaptured(toDataUrl(screenshot));
                        }

                        @Override
                        public void onFailure(int errorCode) {
                            callback.onCaptured("");
                        }
                    }
            );
        } catch (IllegalStateException | SecurityException error) {
            callback.onCaptured("");
        }
    }

    private String toDataUrl(ScreenshotResult screenshot) {
        HardwareBuffer buffer = screenshot.getHardwareBuffer();
        try {
            ColorSpace colorSpace = screenshot.getColorSpace();
            Bitmap hardwareBitmap = Bitmap.wrapHardwareBuffer(buffer, colorSpace);
            if (hardwareBitmap == null) {
                return "";
            }
            Bitmap softwareBitmap = hardwareBitmap.copy(Bitmap.Config.ARGB_8888, false);
            if (softwareBitmap == null) {
                return "";
            }
            Bitmap resized = resize(softwareBitmap, MAX_SCREENSHOT_EDGE);
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            resized.compress(Bitmap.CompressFormat.JPEG, 65, output);
            if (resized != softwareBitmap) {
                resized.recycle();
            }
            softwareBitmap.recycle();
            return "data:image/jpeg;base64," + Base64.getEncoder().encodeToString(output.toByteArray());
        } finally {
            buffer.close();
        }
    }

    private static Bitmap resize(Bitmap source, int maxEdge) {
        int width = source.getWidth();
        int height = source.getHeight();
        int largest = Math.max(width, height);
        if (largest <= maxEdge) {
            return source;
        }
        float scale = (float) maxEdge / largest;
        return Bitmap.createScaledBitmap(
                source,
                Math.max(1, Math.round(width * scale)),
                Math.max(1, Math.round(height * scale)),
                true
        );
    }

    private void resetSession() {
        sessionId = "";
        sessionAppPackage = "";
        stepOrdinal = 0;
        episodeStartedAtElapsed = 0L;
        inFlight = false;
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
