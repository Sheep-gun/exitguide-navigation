package com.exitguide.navigation.executor;

import android.accessibilityservice.AccessibilityService;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.view.animation.DecelerateInterpolator;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

final class NavigationOverlayController {
    static final long CAPTURE_HIDE_DELAY_MS = 60L;

    private static final long TAP_EFFECT_DURATION_MS = 460L;
    private static final int PANEL_MAX_WIDTH_DP = 360;

    private final AccessibilityService service;
    private final WindowManager windowManager;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final List<View> tapViews = new ArrayList<>();

    private LinearLayout statusPanel;
    private View statusDot;
    private TextView statusTitle;
    private TextView statusDetail;
    private boolean captureHidden;
    private boolean closed;
    private String latestMessage = "";

    NavigationOverlayController(AccessibilityService service) {
        this.service = service;
        this.windowManager = (WindowManager) service.getSystemService(AccessibilityService.WINDOW_SERVICE);
    }

    void showStatus(String message) {
        String safeMessage = compact(message);
        if (Looper.myLooper() != Looper.getMainLooper()) {
            handler.post(() -> showStatus(safeMessage));
            return;
        }
        latestMessage = safeMessage;
        if (closed
                || !ExecutorPreferences.progressOverlay(service)
                || (!ExecutorPreferences.active(service) && !terminalMessage(safeMessage))) {
            hideStatusPanel();
            return;
        }
        ensureStatusPanel();
        if (statusPanel == null) {
            return;
        }
        statusTitle.setText(titleFor(safeMessage));
        statusDetail.setText(humanize(safeMessage));
        statusDot.setBackground(circle(stageColor(safeMessage)));
        statusPanel.setVisibility(captureHidden ? View.INVISIBLE : View.VISIBLE);
    }

    void showTap(Rect bounds) {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            Rect copy = bounds == null ? null : new Rect(bounds);
            handler.post(() -> showTap(copy));
            return;
        }
        if (closed
                || captureHidden
                || bounds == null
                || bounds.isEmpty()
                || !ExecutorPreferences.tapIndicator(service)) {
            return;
        }
        int size = dp(44);
        int displayWidth = service.getResources().getDisplayMetrics().widthPixels;
        int displayHeight = service.getResources().getDisplayMetrics().heightPixels;
        int x = clamp(bounds.centerX() - size / 2, 0, Math.max(0, displayWidth - size));
        int y = clamp(bounds.centerY() - size / 2, 0, Math.max(0, displayHeight - size));

        TapPulseView pulse = new TapPulseView(service);
        pulse.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        WindowManager.LayoutParams params = overlayParams(size, size, Gravity.TOP | Gravity.START);
        params.x = x;
        params.y = y;
        params.setTitle("ExitGuide selected candidate");
        try {
            windowManager.addView(pulse, params);
            tapViews.add(pulse);
            pulse.setScaleX(0.55f);
            pulse.setScaleY(0.55f);
            pulse.animate()
                    .scaleX(1.45f)
                    .scaleY(1.45f)
                    .alpha(0f)
                    .setDuration(TAP_EFFECT_DURATION_MS)
                    .setInterpolator(new DecelerateInterpolator())
                    .withEndAction(() -> removeTapView(pulse))
                    .start();
        } catch (RuntimeException ignored) {
            tapViews.remove(pulse);
        }
    }

    void hideForCapture() {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            handler.post(this::hideForCapture);
            return;
        }
        captureHidden = true;
        if (statusPanel != null) {
            statusPanel.setVisibility(View.INVISIBLE);
        }
        for (View tapView : new ArrayList<>(tapViews)) {
            removeTapView(tapView);
        }
    }

    void restoreAfterCapture() {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            handler.post(this::restoreAfterCapture);
            return;
        }
        captureHidden = false;
        if (!closed && !latestMessage.isEmpty() && ExecutorPreferences.progressOverlay(service)) {
            showStatus(latestMessage);
        }
    }

    void close() {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            handler.post(this::close);
            return;
        }
        closed = true;
        for (View tapView : new ArrayList<>(tapViews)) {
            removeTapView(tapView);
        }
        hideStatusPanel();
    }

    private void ensureStatusPanel() {
        if (statusPanel != null || closed) {
            return;
        }
        statusPanel = new LinearLayout(service);
        statusPanel.setOrientation(LinearLayout.HORIZONTAL);
        statusPanel.setGravity(Gravity.CENTER_VERTICAL);
        statusPanel.setPadding(dp(12), dp(9), dp(12), dp(9));
        statusPanel.setElevation(dp(5));
        statusPanel.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);

        GradientDrawable background = new GradientDrawable();
        background.setColor(Color.argb(232, 24, 27, 34));
        background.setCornerRadius(dp(7));
        background.setStroke(dp(1), Color.argb(75, 255, 255, 255));
        statusPanel.setBackground(background);

        statusDot = new View(service);
        LinearLayout.LayoutParams dotParams = new LinearLayout.LayoutParams(dp(9), dp(9));
        dotParams.setMarginEnd(dp(10));
        statusPanel.addView(statusDot, dotParams);

        LinearLayout copy = new LinearLayout(service);
        copy.setOrientation(LinearLayout.VERTICAL);
        statusTitle = new TextView(service);
        statusTitle.setTextColor(Color.WHITE);
        statusTitle.setTextSize(13);
        statusTitle.setTypeface(statusTitle.getTypeface(), android.graphics.Typeface.BOLD);
        statusTitle.setSingleLine(true);
        copy.addView(statusTitle);

        statusDetail = new TextView(service);
        statusDetail.setTextColor(Color.rgb(214, 218, 226));
        statusDetail.setTextSize(11);
        statusDetail.setMaxLines(2);
        statusDetail.setPadding(0, dp(2), 0, 0);
        copy.addView(statusDetail);
        statusPanel.addView(
                copy,
                new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        );

        int availableWidth = Math.max(
                1,
                service.getResources().getDisplayMetrics().widthPixels - dp(32)
        );
        int panelWidth = Math.min(dp(PANEL_MAX_WIDTH_DP), availableWidth);
        WindowManager.LayoutParams params = overlayParams(
                panelWidth,
                WindowManager.LayoutParams.WRAP_CONTENT,
                Gravity.TOP | Gravity.CENTER_HORIZONTAL
        );
        params.y = dp(44);
        params.setTitle("ExitGuide progress");
        try {
            windowManager.addView(statusPanel, params);
        } catch (RuntimeException ignored) {
            statusPanel = null;
            statusDot = null;
            statusTitle = null;
            statusDetail = null;
        }
    }

    private WindowManager.LayoutParams overlayParams(int width, int height, int gravity) {
        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                width,
                height,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                android.graphics.PixelFormat.TRANSLUCENT
        );
        params.gravity = gravity;
        return params;
    }

    private void hideStatusPanel() {
        if (statusPanel == null) {
            return;
        }
        try {
            windowManager.removeViewImmediate(statusPanel);
        } catch (RuntimeException ignored) {
            // Android may already have removed the accessibility window.
        }
        statusPanel = null;
        statusDot = null;
        statusTitle = null;
        statusDetail = null;
    }

    private void removeTapView(View view) {
        if (view == null) {
            return;
        }
        view.animate().cancel();
        tapViews.remove(view);
        try {
            windowManager.removeViewImmediate(view);
        } catch (RuntimeException ignored) {
            // The transient window already completed or the service closed.
        }
    }

    private GradientDrawable circle(int color) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setShape(GradientDrawable.OVAL);
        drawable.setColor(color);
        return drawable;
    }

    private static String titleFor(String message) {
        if (message.startsWith("다음 행동:")) {
            int separator = message.indexOf(" | ");
            return separator < 0 ? message : message.substring(0, separator);
        }
        String lower = message.toLowerCase(Locale.ROOT);
        if (containsAny(lower, "destination_reached", "목적지에 도달", "목적 달성")) {
            return "목적 달성";
        }
        if (containsAny(lower, "모호", "애매", "visual_reobserve", "no_change", "unchanged", "wrong_destination")) {
            return "화면이 애매함";
        }
        if (containsAny(lower, "사용자 확인", "사용자가 직접", "안전 경계", "confirmation")) {
            return "사용자 확인 필요";
        }
        if (containsAny(lower, "다시 관찰", "재확인", "재시도")) {
            return "경로 다시 찾는 중";
        }
        if (containsAny(lower, "오류", "실패", "차단", "중지")) {
            return "진행 중단";
        }
        if (containsAny(lower, "판단", "다음 안전 행동")) {
            return "다음 행동 결정 중";
        }
        if (containsAny(lower, "클릭", "후보 id")) {
            return "항목 선택";
        }
        if (containsAny(lower, "스크롤", "화면 이동")) {
            return "화면 이동 중";
        }
        if (containsAny(lower, "복구", "다시 관찰")) {
            return "경로 다시 찾는 중";
        }
        if (containsAny(lower, "관찰 결과", "화면 변화")) {
            return "행동 결과 확인";
        }
        if (containsAny(lower, "화면", "접근성 구조", "관찰")) {
            return "화면 분석 중";
        }
        if (containsAny(lower, "api", "연결")) {
            return "서버 연결 확인";
        }
        return "ExitGuide 진행 상황";
    }

    private static int stageColor(String message) {
        if (message.startsWith("다음 행동:")) {
            return message.contains("사용자 확인")
                    ? Color.rgb(255, 184, 77)
                    : Color.rgb(78, 148, 255);
        }
        String title = titleFor(message);
        if ("목적 달성".equals(title)) {
            return Color.rgb(61, 201, 126);
        }
        if ("화면이 애매함".equals(title) || "사용자 확인 필요".equals(title)) {
            return Color.rgb(255, 184, 77);
        }
        if ("진행 중단".equals(title)) {
            return Color.rgb(255, 93, 93);
        }
        return Color.rgb(78, 148, 255);
    }

    private static String humanize(String message) {
        String detail = message;
        if (message.startsWith("다음 행동:")) {
            int separator = message.indexOf(" | ");
            detail = separator < 0 ? "" : message.substring(separator + 3);
        }
        return detail
                .replace("destination_reached", "목적지 도달")
                .replace("no_change", "화면 변화 없음")
                .replace("wrong_destination", "다른 화면에 도착")
                .replace("repeated_screen", "같은 화면 반복")
                .replace("progressed", "목표에 가까워짐")
                .replace("unchanged", "진전 없음")
                .replace("regressed", "목표에서 멀어짐");
    }

    private static String compact(String value) {
        if (value == null || value.trim().isEmpty()) {
            return "대기 중";
        }
        String compact = value.trim().replaceAll("\\s+", " ");
        return compact.length() <= 180 ? compact : compact.substring(0, 177) + "...";
    }

    private static boolean containsAny(String value, String... needles) {
        for (String needle : needles) {
            if (value.contains(needle)) {
                return true;
            }
        }
        return false;
    }

    private static boolean terminalMessage(String message) {
        String title = titleFor(message);
        return "목적 달성".equals(title)
                || "사용자 확인 필요".equals(title)
                || "진행 중단".equals(title);
    }

    private int dp(int value) {
        return Math.round(value * service.getResources().getDisplayMetrics().density);
    }

    private static int clamp(int value, int minimum, int maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    private static final class TapPulseView extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

        TapPulseView(AccessibilityService service) {
            super(service);
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            float centerX = getWidth() / 2f;
            float centerY = getHeight() / 2f;
            float unit = getResources().getDisplayMetrics().density;
            paint.setColor(Color.argb(235, 244, 45, 45));
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(3f * unit);
            canvas.drawCircle(centerX, centerY, 14f * unit, paint);
            paint.setStyle(Paint.Style.FILL);
            canvas.drawCircle(centerX, centerY, 5f * unit, paint);
        }
    }
}
