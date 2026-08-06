package com.exitguide.navigation.executor;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * ADB-only bridge for collector control and installation diagnostics.
 *
 * <p>The exported receiver requires Android's signature-level DUMP permission,
 * which the ADB shell owns. Accessibility actions are still grounded and
 * safety-checked by the service and server before execution.</p>
 */
public final class ExecutorDiagnosticReceiver extends BroadcastReceiver {
    private static final String LOG_TAG = "ExitGuideNavigationExecutor";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (ExecutorPreferences.ACTION_ADB_HEARTBEAT.equals(action)) {
            ExecutorPreferences.recordAdbHeartbeat(context);
            context.sendBroadcast(
                    new Intent(ExecutorPreferences.ACTION_ADB_HEARTBEAT_INTERNAL)
                            .setPackage(context.getPackageName())
            );
            setResultCode(AdbConnectionLease.ACCEPTED_RESULT_CODE);
            return;
        }
        if (ExecutorPreferences.ACTION_ADB_START_NAVIGATION.equals(action)) {
            String goal = value(intent.getStringExtra("goal"));
            String apiBaseUrl = value(intent.getStringExtra("api_base_url"));
            String collectorAlias = value(intent.getStringExtra("collector_alias"));
            if (goal.isEmpty()) {
                Log.w(LOG_TAG, "adb_control start_rejected reason=empty_goal");
                return;
            }
            if (apiBaseUrl.isEmpty()) {
                apiBaseUrl = ExecutorPreferences.apiBaseUrl(context);
            }
            if (collectorAlias.isEmpty()) {
                collectorAlias = ExecutorPreferences.collectorAlias(context);
            }
            // The start command itself proves that the exact ADB device is connected.
            // This closes the short gap before the hidden monitor's first heartbeat.
            ExecutorPreferences.recordAdbHeartbeat(context);
            ExecutorPreferences.clearOperatorCommand(context);
            ExecutorPreferences.setTaskPreconditions(
                    context,
                    valueOr(intent, "account_state", "unknown"),
                    valueOr(intent, "service_state", "unknown"),
                    valueOr(intent, "start_surface", ""),
                    valueOr(intent, "precondition_status", "unknown"),
                    valueOr(intent, "reset_method", ""),
                    intent.getBooleanExtra("reset_verified", false),
                    valueOr(intent, "precondition_source", "unknown"),
                    boundedConfidence(intent.getFloatExtra("precondition_confidence", -1.0f))
            );
            ExecutorPreferences.configure(
                    context,
                    apiBaseUrl,
                    goal,
                    collectorAlias,
                    ExecutorPreferences.testAccount(context),
                    true
            );
            Log.i(LOG_TAG, "adb_control started goal_chars=" + goal.length());
            return;
        }
        if (ExecutorPreferences.ACTION_ADB_STOP_NAVIGATION.equals(action)) {
            ExecutorPreferences.clearOperatorCommand(context);
            ExecutorPreferences.setActive(context, false);
            Log.i(LOG_TAG, "adb_control stopped");
            return;
        }
        if (ExecutorPreferences.ACTION_ADB_OPERATOR_ACTION.equals(action)) {
            String actionName = value(intent.getStringExtra("action_name"));
            String candidateId = value(intent.getStringExtra("candidate_id"));
            String direction = value(intent.getStringExtra("direction"));
            String commandId = value(intent.getStringExtra("command_id"));
            String expectedScreen = value(intent.getStringExtra("expected_screen_fingerprint"));
            String reasonCodes = value(intent.getStringExtra("reason_codes"));
            String reasonText = value(intent.getStringExtra("reason_text"));
            String reviewStatus = valueOr(intent, "review_status", "unreviewed");
            if (!ExecutorPreferences.active(context)
                    || !ExecutorPreferences.hasFreshAdbLease(context)
                    || !NavigationSafetyPolicy.isAllowedAction(actionName)
                    || commandId.isEmpty()
                    || expectedScreen.isEmpty()
                    || reasonCodes.isEmpty()
                    || ("click".equals(actionName) && candidateId.isEmpty())
                    || ("scroll".equals(actionName)
                            && !("up".equals(direction) || "down".equals(direction)))
                    || !("unreviewed".equals(reviewStatus)
                            || "provisional".equals(reviewStatus)
                            || "verified".equals(reviewStatus))) {
                Log.w(LOG_TAG, "adb_control operator_action_rejected reason=invalid_command");
                return;
            }
            boolean saved = ExecutorPreferences.saveOperatorCommand(
                    context,
                    new ExecutorPreferences.OperatorCommand(
                            actionName,
                            candidateId,
                            direction,
                            commandId,
                            expectedScreen,
                            reasonCodes,
                            reasonText,
                            reviewStatus
                    )
            );
            Log.i(
                    LOG_TAG,
                    "adb_control operator_action_saved=" + saved
                            + " command_id=" + commandId
                            + " action=" + actionName
            );
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

    private static String valueOr(Intent intent, String key, String fallback) {
        String result = value(intent.getStringExtra(key));
        return result.isEmpty() ? fallback : result;
    }

    private static float boundedConfidence(float value) {
        return value < 0.0f ? -1.0f : Math.min(1.0f, value);
    }
}
