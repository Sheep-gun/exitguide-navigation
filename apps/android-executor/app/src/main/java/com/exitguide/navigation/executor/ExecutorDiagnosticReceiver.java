package com.exitguide.navigation.executor;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * ADB-only bridge for non-mutating installation diagnostics.
 *
 * <p>The exported receiver requires Android's signature-level DUMP permission,
 * which the ADB shell owns. It forwards the request as an app-internal
 * broadcast; it never starts navigation or executes an accessibility action.</p>
 */
public final class ExecutorDiagnosticReceiver extends BroadcastReceiver {
    private static final String LOG_TAG = "ExitGuideNavigationExecutor";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (ExecutorPreferences.ACTION_ADB_START_NAVIGATION.equals(action)) {
            String goal = value(intent.getStringExtra("goal"));
            String apiBaseUrl = value(intent.getStringExtra("api_base_url"));
            if (goal.isEmpty()) {
                Log.w(LOG_TAG, "adb_control start_rejected reason=empty_goal");
                return;
            }
            if (apiBaseUrl.isEmpty()) {
                apiBaseUrl = ExecutorPreferences.apiBaseUrl(context);
            }
            ExecutorPreferences.configure(context, apiBaseUrl, goal, true);
            Log.i(LOG_TAG, "adb_control started goal_chars=" + goal.length());
            return;
        }
        if (ExecutorPreferences.ACTION_ADB_STOP_NAVIGATION.equals(action)) {
            ExecutorPreferences.setActive(context, false);
            Log.i(LOG_TAG, "adb_control stopped");
            return;
        }
        if (!ExecutorPreferences.ACTION_DIAGNOSTIC_REQUEST.equals(action)) {
            Log.w(LOG_TAG, "adb_control rejected_unknown_action");
            return;
        }
        // Diagnostics must never resume a previously active navigation episode.
        ExecutorPreferences.setActive(context, false);
        Intent internal = new Intent(ExecutorPreferences.ACTION_DIAGNOSTIC_INTERNAL)
                .setPackage(context.getPackageName())
                .putExtra("request_id", intent.getStringExtra("request_id"))
                .putExtra("api_base_url", intent.getStringExtra("api_base_url"));
        context.sendBroadcast(internal);
    }

    private static String value(String value) {
        return value == null ? "" : value.trim();
    }
}
