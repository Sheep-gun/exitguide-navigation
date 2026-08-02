package com.exitguide.navigation.executor;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.net.MalformedURLException;
import java.net.URL;
import java.util.List;

public final class MainActivity extends Activity {
    private EditText apiBaseUrl;
    private EditText goal;
    private TextView accessibilityState;
    private TextView runtimeStatus;

    private final BroadcastReceiver statusReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            runtimeStatus.setText(intent.getStringExtra("status"));
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildContent());
    }

    @Override
    protected void onStart() {
        super.onStart();
        IntentFilter filter = new IntentFilter(ExecutorPreferences.ACTION_STATUS_CHANGED);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(statusReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(statusReceiver, filter);
        }
    }

    @Override
    protected void onStop() {
        unregisterReceiver(statusReceiver);
        super.onStop();
    }

    @Override
    protected void onResume() {
        super.onResume();
        accessibilityState.setText(
                isAccessibilityServiceEnabled()
                        ? "접근성 서비스 활성화됨"
                        : "접근성 서비스 비활성화됨"
        );
        runtimeStatus.setText(ExecutorPreferences.status(this));
    }

    private View buildContent() {
        int padding = dp(20);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(padding, padding, padding, padding);

        content.addView(text("ExitGuide Navigation Executor", 24, Color.rgb(25, 32, 52)), matchWrap());
        TextView description = text(
                "현재 화면에서 실제 발견된 후보 ID만 API가 선택할 수 있습니다. "
                        + "좌표 클릭, 입력, 결제·탈퇴·해지 확정 같은 위험 행동은 실행하지 않습니다.",
                15,
                Color.DKGRAY
        );
        description.setPadding(0, dp(10), 0, dp(18));
        content.addView(description, matchWrap());

        content.addView(text("Navigation API", 14, Color.DKGRAY), matchWrap());
        apiBaseUrl = new EditText(this);
        apiBaseUrl.setSingleLine(true);
        apiBaseUrl.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        apiBaseUrl.setText(ExecutorPreferences.apiBaseUrl(this));
        content.addView(apiBaseUrl, matchWrap());

        content.addView(text("사용자 목적", 14, Color.DKGRAY), matchWrap());
        goal = new EditText(this);
        goal.setMinLines(2);
        goal.setHint("예: 회원 탈퇴 메뉴를 찾아줘");
        goal.setText(ExecutorPreferences.goal(this));
        content.addView(goal, matchWrap());

        accessibilityState = text("", 15, Color.rgb(30, 70, 150));
        accessibilityState.setPadding(0, dp(12), 0, dp(8));
        content.addView(accessibilityState, matchWrap());

        Button settingsButton = new Button(this);
        settingsButton.setText("접근성 설정 열기");
        settingsButton.setOnClickListener(
                view -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        );
        content.addView(settingsButton, matchWrap());

        Button startButton = new Button(this);
        startButton.setText("안전 탐색 시작");
        startButton.setOnClickListener(view -> startNavigation());
        content.addView(startButton, matchWrap());

        Button stopButton = new Button(this);
        stopButton.setText("탐색 중지");
        stopButton.setOnClickListener(view -> {
            ExecutorPreferences.setActive(this, false);
            ExecutorPreferences.publishStatus(this, "사용자가 탐색을 중지했습니다.");
        });
        content.addView(stopButton, matchWrap());

        runtimeStatus = text(ExecutorPreferences.status(this), 15, Color.rgb(35, 35, 35));
        runtimeStatus.setPadding(0, dp(16), 0, dp(24));
        content.addView(runtimeStatus, matchWrap());

        ScrollView scrollView = new ScrollView(this);
        scrollView.addView(content);
        return scrollView;
    }

    private void startNavigation() {
        String baseUrl = apiBaseUrl.getText().toString().trim();
        String goalText = goal.getText().toString().trim();
        if (!isValidHttpUrl(baseUrl)) {
            Toast.makeText(this, "http 또는 https Navigation API 주소를 확인하세요.", Toast.LENGTH_LONG).show();
            return;
        }
        if (goalText.isEmpty()) {
            Toast.makeText(this, "사용자 목적을 입력하세요.", Toast.LENGTH_LONG).show();
            return;
        }
        if (!isAccessibilityServiceEnabled()) {
            Toast.makeText(this, "먼저 ExitGuide 접근성 서비스를 활성화하세요.", Toast.LENGTH_LONG).show();
            startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
            return;
        }
        ExecutorPreferences.configure(this, baseUrl, goalText, true);
        ExecutorPreferences.publishStatus(this, "현재 화면을 관찰하는 중입니다.");
        moveTaskToBack(true);
    }

    private boolean isAccessibilityServiceEnabled() {
        AccessibilityManager manager =
                (AccessibilityManager) getSystemService(Context.ACCESSIBILITY_SERVICE);
        List<AccessibilityServiceInfo> services = manager.getEnabledAccessibilityServiceList(
                AccessibilityServiceInfo.FEEDBACK_ALL_MASK
        );
        String serviceName = ExitGuideAccessibilityService.class.getName();
        for (AccessibilityServiceInfo info : services) {
            if (info.getResolveInfo() != null
                    && info.getResolveInfo().serviceInfo != null
                    && matchesAccessibilityService(
                            getPackageName(),
                            serviceName,
                            info.getResolveInfo().serviceInfo.packageName,
                            info.getResolveInfo().serviceInfo.name
                    )) {
                return true;
            }
        }
        return false;
    }

    static boolean matchesAccessibilityService(
            String expectedPackage,
            String expectedClass,
            String actualPackage,
            String actualClass
    ) {
        if (expectedPackage == null || expectedClass == null
                || actualPackage == null || actualClass == null
                || !expectedPackage.equals(actualPackage)) {
            return false;
        }
        String normalizedClass = actualClass;
        if (actualClass.startsWith(".")) {
            normalizedClass = actualPackage + actualClass;
        } else if (!actualClass.contains(".")) {
            normalizedClass = actualPackage + "." + actualClass;
        }
        return expectedClass.equals(normalizedClass);
    }

    private static boolean isValidHttpUrl(String value) {
        try {
            URL url = new URL(value);
            return ("http".equals(url.getProtocol()) || "https".equals(url.getProtocol()))
                    && url.getHost() != null
                    && !url.getHost().isEmpty();
        } catch (MalformedURLException error) {
            return false;
        }
    }

    private TextView text(String value, int sp, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sp);
        view.setTextColor(color);
        return view;
    }

    private static LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
