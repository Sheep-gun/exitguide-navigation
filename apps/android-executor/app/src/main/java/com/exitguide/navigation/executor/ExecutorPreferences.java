package com.exitguide.navigation.executor;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

final class ExecutorPreferences {
    static final String ACTION_CONFIGURATION_CHANGED =
            "com.exitguide.navigation.executor.CONFIGURATION_CHANGED";
    static final String ACTION_STATUS_CHANGED =
            "com.exitguide.navigation.executor.STATUS_CHANGED";
    static final String ACTION_DIAGNOSTIC_REQUEST =
            "com.exitguide.navigation.executor.DIAGNOSTIC_SNAPSHOT";
    static final String ACTION_DIAGNOSTIC_INTERNAL =
            "com.exitguide.navigation.executor.DIAGNOSTIC_SNAPSHOT_INTERNAL";
    static final String ACTION_ADB_START_NAVIGATION =
            "com.exitguide.navigation.executor.ADB_START_NAVIGATION";
    static final String ACTION_ADB_STOP_NAVIGATION =
            "com.exitguide.navigation.executor.ADB_STOP_NAVIGATION";

    private static final String FILE_NAME = "navigation_executor";
    private static final String KEY_API_BASE_URL = "api_base_url";
    private static final String KEY_GOAL = "goal";
    private static final String KEY_ACTIVE = "active";
    private static final String KEY_STATUS = "status";

    private ExecutorPreferences() {}

    static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences(FILE_NAME, Context.MODE_PRIVATE);
    }

    static String apiBaseUrl(Context context) {
        return preferences(context).getString(
                KEY_API_BASE_URL,
                BuildConfig.DEFAULT_NAVIGATION_API
        ).trim();
    }

    static String goal(Context context) {
        return preferences(context).getString(KEY_GOAL, "").trim();
    }

    static boolean active(Context context) {
        return preferences(context).getBoolean(KEY_ACTIVE, false);
    }

    static String status(Context context) {
        return preferences(context).getString(KEY_STATUS, "대기 중");
    }

    static void configure(Context context, String apiBaseUrl, String goal, boolean active) {
        preferences(context).edit()
                .putString(KEY_API_BASE_URL, apiBaseUrl.trim())
                .putString(KEY_GOAL, goal.trim())
                .putBoolean(KEY_ACTIVE, active)
                .apply();
        context.sendBroadcast(
                new Intent(ACTION_CONFIGURATION_CHANGED).setPackage(context.getPackageName())
        );
    }

    static void setActive(Context context, boolean active) {
        preferences(context).edit().putBoolean(KEY_ACTIVE, active).apply();
        context.sendBroadcast(
                new Intent(ACTION_CONFIGURATION_CHANGED).setPackage(context.getPackageName())
        );
    }

    static void publishStatus(Context context, String status) {
        preferences(context).edit().putString(KEY_STATUS, status).apply();
        context.sendBroadcast(
                new Intent(ACTION_STATUS_CHANGED)
                        .setPackage(context.getPackageName())
                        .putExtra("status", status)
        );
    }
}
