package com.exitguide.navigation.executor;

import android.content.Context;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;

final class LatestScreenStore {
    private static final String DIRECTORY = "collector";
    private static final String FILE_NAME = "latest-screen.json";

    private LatestScreenStore() {}

    static void write(
            Context context,
            AccessibilityScreenReader.ScreenSnapshot snapshot,
            String goal,
            String appVersion,
            String sessionId,
            int stepOrdinal
    ) throws IOException, JSONException {
        File directory = new File(context.getFilesDir(), DIRECTORY);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IOException("cannot create collector state directory");
        }
        JSONObject payload = new JSONObject();
        payload.put("schema_version", "collector-latest-screen.v1");
        payload.put("captured_at", CollectionRunMetadata.now());
        payload.put("goal_text", goal);
        payload.put("app_package", snapshot.appPackage);
        payload.put("app_version", appVersion);
        payload.put("screen_fingerprint", snapshot.screenFingerprint);
        payload.put("session_id", sessionId);
        payload.put("step_ordinal", stepOrdinal);
        payload.put("task_context", CollectionRunMetadata.taskContext(context));
        payload.put("screen", snapshot.payload);

        File target = new File(directory, FILE_NAME);
        File temporary = new File(directory, FILE_NAME + ".tmp");
        byte[] bytes = payload.toString(2).getBytes(StandardCharsets.UTF_8);
        try (FileOutputStream stream = new FileOutputStream(temporary, false)) {
            stream.write(bytes);
            stream.getFD().sync();
        }
        try {
            Files.move(
                    temporary.toPath(),
                    target.toPath(),
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING
            );
        } catch (AtomicMoveNotSupportedException ignored) {
            Files.move(
                    temporary.toPath(),
                    target.toPath(),
                    StandardCopyOption.REPLACE_EXISTING
            );
        }
    }
}
