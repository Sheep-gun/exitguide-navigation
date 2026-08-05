package com.exitguide.navigation.executor;

import android.content.Context;
import android.content.res.Configuration;
import android.os.Build;
import android.util.DisplayMetrics;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.time.Instant;
import java.util.Locale;
import java.util.UUID;

final class CollectionRunMetadata {
    private CollectionRunMetadata() {}

    static String newRunId() {
        return "navrun_" + UUID.randomUUID().toString().replace("-", "");
    }

    static String now() {
        return Instant.now().toString();
    }

    static JSONObject build(
            Context context,
            String runId,
            String collectionBatchId,
            String startedAt
    ) throws JSONException {
        Configuration configuration = context.getResources().getConfiguration();
        DisplayMetrics metrics = context.getResources().getDisplayMetrics();
        Locale locale = configuration.getLocales().isEmpty()
                ? Locale.getDefault()
                : configuration.getLocales().get(0);
        boolean testAccount = ExecutorPreferences.testAccount(context);

        JSONObject payload = new JSONObject();
        payload.put("run_id", runId);
        payload.put("collection_batch_id", collectionBatchId);
        payload.put("collector_alias", ExecutorPreferences.collectorAlias(context));
        payload.put("device_instance_id", ExecutorPreferences.deviceInstanceId(context));
        payload.put("manufacturer", safe(Build.MANUFACTURER));
        payload.put("model", safe(Build.MODEL));
        payload.put("android_api_level", Build.VERSION.SDK_INT);
        payload.put("android_release", safe(Build.VERSION.RELEASE));
        payload.put("display_width_px", metrics.widthPixels);
        payload.put("display_height_px", metrics.heightPixels);
        payload.put("density_dpi", metrics.densityDpi);
        payload.put("font_scale", configuration.fontScale);
        payload.put("ui_mode", uiMode(configuration));
        payload.put(
                "orientation",
                configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
                        ? "landscape"
                        : configuration.orientation == Configuration.ORIENTATION_PORTRAIT
                                ? "portrait" : "unknown"
        );
        payload.put("locale", locale.toLanguageTag());
        payload.put("collector_app_version", BuildConfig.VERSION_NAME);
        payload.put("collector_build_id", BuildConfig.COLLECTOR_BUILD_ID);
        payload.put("executor_version", BuildConfig.VERSION_NAME);
        payload.put("executor_build_id", BuildConfig.COLLECTOR_BUILD_ID);
        payload.put("run_mode", "agent");
        payload.put("artifact_policy", testAccount ? "test_account_restricted" : "none");
        payload.put("test_account", testAccount);
        payload.put("started_at", startedAt);
        return payload;
    }

    static JSONObject taskContext(Context context) throws JSONException {
        JSONObject payload = new JSONObject();
        payload.put("task_source", "human");
        payload.put("task_id", "");
        payload.put("goal_parameters_redacted", new JSONObject());
        JSONArray constraints = new JSONArray();
        constraints.put("no_state_changing_final_action");
        payload.put("task_constraints", constraints);
        payload.put("success_spec_id", "navigation_destination_v1");
        payload.put("success_spec_version", "1");
        payload.put("account_state", ExecutorPreferences.accountState(context));
        payload.put("service_state", ExecutorPreferences.serviceState(context));
        payload.put("start_surface", ExecutorPreferences.startSurface(context));
        payload.put("precondition_status", ExecutorPreferences.preconditionStatus(context));
        payload.put("reset_method", ExecutorPreferences.resetMethod(context));
        payload.put("reset_verified", ExecutorPreferences.resetVerified(context));
        payload.put("precondition_source", ExecutorPreferences.preconditionSource(context));
        float confidence = ExecutorPreferences.preconditionConfidence(context);
        if (confidence < 0.0f) {
            payload.put("precondition_confidence", JSONObject.NULL);
        } else {
            payload.put("precondition_confidence", confidence);
        }
        return payload;
    }

    private static String uiMode(Configuration configuration) {
        int mode = configuration.uiMode & Configuration.UI_MODE_NIGHT_MASK;
        if (mode == Configuration.UI_MODE_NIGHT_YES) {
            return "dark";
        }
        if (mode == Configuration.UI_MODE_NIGHT_NO) {
            return "light";
        }
        return "unknown";
    }

    private static String safe(String value) {
        return value == null ? "" : value;
    }
}
