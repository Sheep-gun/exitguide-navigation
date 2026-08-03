package com.exitguide.navigation.executor;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * ADB-only bridge for non-mutating installation diagnostics.
 *
 * <p>The exported receiver requires Android's signature-level DUMP permission,
 * which the ADB shell owns. It forwards the request as an app-internal
 * broadcast; it never starts navigation or executes an accessibility action.</p>
 */
public final class ExecutorDiagnosticReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        // Diagnostics must never resume a previously active navigation episode.
        ExecutorPreferences.setActive(context, false);
        Intent internal = new Intent(ExecutorPreferences.ACTION_DIAGNOSTIC_INTERNAL)
                .setPackage(context.getPackageName())
                .putExtra("request_id", intent.getStringExtra("request_id"))
                .putExtra("api_base_url", intent.getStringExtra("api_base_url"));
        context.sendBroadcast(internal);
    }
}
