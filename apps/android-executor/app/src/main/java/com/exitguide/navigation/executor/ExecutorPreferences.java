package com.exitguide.navigation.executor;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

import java.util.UUID;

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
    static final String ACTION_ADB_OPERATOR_ACTION =
            "com.exitguide.navigation.executor.ADB_OPERATOR_ACTION";
    static final String ACTION_OPERATOR_COMMAND_CHANGED =
            "com.exitguide.navigation.executor.OPERATOR_COMMAND_CHANGED";

    private static final String FILE_NAME = "navigation_executor";
    private static final String KEY_API_BASE_URL = "api_base_url";
    private static final String KEY_GOAL = "goal";
    private static final String KEY_ACTIVE = "active";
    private static final String KEY_STATUS = "status";
    private static final String KEY_COLLECTOR_ALIAS = "collector_alias";
    private static final String KEY_TEST_ACCOUNT = "test_account";
    private static final String KEY_DEVICE_INSTANCE_ID = "device_instance_id";
    private static final String KEY_PROGRESS_OVERLAY = "progress_overlay";
    private static final String KEY_TAP_INDICATOR = "tap_indicator";
    private static final String KEY_DECISION_MODE = "decision_mode";
    private static final String KEY_ACCOUNT_STATE = "account_state";
    private static final String KEY_SERVICE_STATE = "service_state";
    private static final String KEY_START_SURFACE = "start_surface";
    private static final String KEY_PRECONDITION_STATUS = "precondition_status";
    private static final String KEY_RESET_METHOD = "reset_method";
    private static final String KEY_RESET_VERIFIED = "reset_verified";
    private static final String KEY_PRECONDITION_SOURCE = "precondition_source";
    private static final String KEY_PRECONDITION_CONFIDENCE = "precondition_confidence";
    private static final String KEY_OPERATOR_ACTION_NAME = "operator_action_name";
    private static final String KEY_OPERATOR_CANDIDATE_ID = "operator_candidate_id";
    private static final String KEY_OPERATOR_DIRECTION = "operator_direction";
    private static final String KEY_OPERATOR_COMMAND_ID = "operator_command_id";
    private static final String KEY_OPERATOR_EXPECTED_SCREEN = "operator_expected_screen";
    private static final String KEY_OPERATOR_REASON_CODES = "operator_reason_codes";
    private static final String KEY_OPERATOR_REASON_TEXT = "operator_reason_text";
    private static final String KEY_OPERATOR_REVIEW_STATUS = "operator_review_status";

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

    static String collectorAlias(Context context) {
        return preferences(context).getString(KEY_COLLECTOR_ALIAS, "unassigned").trim();
    }

    static boolean testAccount(Context context) {
        return preferences(context).getBoolean(KEY_TEST_ACCOUNT, false);
    }

    static boolean progressOverlay(Context context) {
        return preferences(context).getBoolean(KEY_PROGRESS_OVERLAY, true);
    }

    static boolean tapIndicator(Context context) {
        return preferences(context).getBoolean(KEY_TAP_INDICATOR, true);
    }

    static boolean codexOperatorMode(Context context) {
        return "codex_operator".equals(
                preferences(context).getString(KEY_DECISION_MODE, "codex_operator")
        );
    }

    static String accountState(Context context) {
        return preferences(context).getString(KEY_ACCOUNT_STATE, "unknown").trim();
    }

    static String serviceState(Context context) {
        return preferences(context).getString(KEY_SERVICE_STATE, "unknown").trim();
    }

    static String startSurface(Context context) {
        return preferences(context).getString(KEY_START_SURFACE, "").trim();
    }

    static String preconditionStatus(Context context) {
        return preferences(context).getString(KEY_PRECONDITION_STATUS, "unknown").trim();
    }

    static String resetMethod(Context context) {
        return preferences(context).getString(KEY_RESET_METHOD, "").trim();
    }

    static boolean resetVerified(Context context) {
        return preferences(context).getBoolean(KEY_RESET_VERIFIED, false);
    }

    static String preconditionSource(Context context) {
        return preferences(context).getString(KEY_PRECONDITION_SOURCE, "unknown").trim();
    }

    static float preconditionConfidence(Context context) {
        return preferences(context).getFloat(KEY_PRECONDITION_CONFIDENCE, -1.0f);
    }

    static String deviceInstanceId(Context context) {
        SharedPreferences preferences = preferences(context);
        String existing = preferences.getString(KEY_DEVICE_INSTANCE_ID, "").trim();
        if (!existing.isEmpty()) {
            return existing;
        }
        String generated = "device_" + UUID.randomUUID().toString().replace("-", "");
        preferences.edit().putString(KEY_DEVICE_INSTANCE_ID, generated).apply();
        return generated;
    }

    static void configure(Context context, String apiBaseUrl, String goal, boolean active) {
        configure(
                context,
                apiBaseUrl,
                goal,
                collectorAlias(context),
                testAccount(context),
                progressOverlay(context),
                tapIndicator(context),
                active
        );
    }

    static void configure(
            Context context,
            String apiBaseUrl,
            String goal,
            String collectorAlias,
            boolean testAccount,
            boolean active
    ) {
        configure(
                context,
                apiBaseUrl,
                goal,
                collectorAlias,
                testAccount,
                progressOverlay(context),
                tapIndicator(context),
                active
        );
    }

    static void configure(
            Context context,
            String apiBaseUrl,
            String goal,
            String collectorAlias,
            boolean testAccount,
            boolean progressOverlay,
            boolean tapIndicator,
            boolean active
    ) {
        preferences(context).edit()
                .putString(KEY_API_BASE_URL, apiBaseUrl.trim())
                .putString(KEY_GOAL, goal.trim())
                .putString(KEY_COLLECTOR_ALIAS, collectorAlias.trim())
                .putBoolean(KEY_TEST_ACCOUNT, testAccount)
                .putBoolean(KEY_PROGRESS_OVERLAY, progressOverlay)
                .putBoolean(KEY_TAP_INDICATOR, tapIndicator)
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

    static void setTaskPreconditions(
            Context context,
            String accountState,
            String serviceState,
            String startSurface,
            String preconditionStatus,
            String resetMethod,
            boolean resetVerified,
            String preconditionSource,
            float preconditionConfidence
    ) {
        preferences(context).edit()
                .putString(KEY_ACCOUNT_STATE, valueOr(accountState, "unknown"))
                .putString(KEY_SERVICE_STATE, valueOr(serviceState, "unknown"))
                .putString(KEY_START_SURFACE, valueOr(startSurface, ""))
                .putString(KEY_PRECONDITION_STATUS, valueOr(preconditionStatus, "unknown"))
                .putString(KEY_RESET_METHOD, valueOr(resetMethod, ""))
                .putBoolean(KEY_RESET_VERIFIED, resetVerified)
                .putString(KEY_PRECONDITION_SOURCE, valueOr(preconditionSource, "unknown"))
                .putFloat(KEY_PRECONDITION_CONFIDENCE, preconditionConfidence)
                .apply();
    }

    static boolean saveOperatorCommand(Context context, OperatorCommand command) {
        boolean saved = preferences(context).edit()
                .putString(KEY_OPERATOR_ACTION_NAME, command.actionName)
                .putString(KEY_OPERATOR_CANDIDATE_ID, command.candidateId)
                .putString(KEY_OPERATOR_DIRECTION, command.direction)
                .putString(KEY_OPERATOR_EXPECTED_SCREEN, command.expectedScreenFingerprint)
                .putString(KEY_OPERATOR_REASON_CODES, command.reasonCodesCsv)
                .putString(KEY_OPERATOR_REASON_TEXT, command.reasonText)
                .putString(KEY_OPERATOR_REVIEW_STATUS, command.reviewStatus)
                .putString(KEY_OPERATOR_COMMAND_ID, command.commandId)
                .commit();
        if (saved) {
            context.sendBroadcast(
                    new Intent(ACTION_OPERATOR_COMMAND_CHANGED).setPackage(context.getPackageName())
            );
        }
        return saved;
    }

    static OperatorCommand pendingOperatorCommand(Context context) {
        SharedPreferences preferences = preferences(context);
        String commandId = preferences.getString(KEY_OPERATOR_COMMAND_ID, "").trim();
        if (commandId.isEmpty()) {
            return null;
        }
        return new OperatorCommand(
                preferences.getString(KEY_OPERATOR_ACTION_NAME, "").trim(),
                preferences.getString(KEY_OPERATOR_CANDIDATE_ID, "").trim(),
                preferences.getString(KEY_OPERATOR_DIRECTION, "").trim(),
                commandId,
                preferences.getString(KEY_OPERATOR_EXPECTED_SCREEN, "").trim(),
                preferences.getString(KEY_OPERATOR_REASON_CODES, "").trim(),
                preferences.getString(KEY_OPERATOR_REASON_TEXT, "").trim(),
                preferences.getString(KEY_OPERATOR_REVIEW_STATUS, "unreviewed").trim()
        );
    }

    static void clearOperatorCommand(Context context) {
        preferences(context).edit()
                .remove(KEY_OPERATOR_ACTION_NAME)
                .remove(KEY_OPERATOR_CANDIDATE_ID)
                .remove(KEY_OPERATOR_DIRECTION)
                .remove(KEY_OPERATOR_COMMAND_ID)
                .remove(KEY_OPERATOR_EXPECTED_SCREEN)
                .remove(KEY_OPERATOR_REASON_CODES)
                .remove(KEY_OPERATOR_REASON_TEXT)
                .remove(KEY_OPERATOR_REVIEW_STATUS)
                .commit();
    }

    static void publishStatus(Context context, String status) {
        preferences(context).edit().putString(KEY_STATUS, status).apply();
        context.sendBroadcast(
                new Intent(ACTION_STATUS_CHANGED)
                        .setPackage(context.getPackageName())
                        .putExtra("status", status)
        );
    }

    private static String valueOr(String value, String fallback) {
        String normalized = value == null ? "" : value.trim();
        return normalized.isEmpty() ? fallback : normalized;
    }

    static final class OperatorCommand {
        final String actionName;
        final String candidateId;
        final String direction;
        final String commandId;
        final String expectedScreenFingerprint;
        final String reasonCodesCsv;
        final String reasonText;
        final String reviewStatus;

        OperatorCommand(
                String actionName,
                String candidateId,
                String direction,
                String commandId,
                String expectedScreenFingerprint,
                String reasonCodesCsv,
                String reasonText,
                String reviewStatus
        ) {
            this.actionName = valueOr(actionName, "");
            this.candidateId = valueOr(candidateId, "");
            this.direction = valueOr(direction, "");
            this.commandId = valueOr(commandId, "");
            this.expectedScreenFingerprint = valueOr(expectedScreenFingerprint, "");
            this.reasonCodesCsv = valueOr(reasonCodesCsv, "");
            this.reasonText = valueOr(reasonText, "");
            this.reviewStatus = valueOr(reviewStatus, "unreviewed");
        }
    }
}
