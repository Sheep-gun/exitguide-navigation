package com.exitguide.navigation.executor;

import android.os.Handler;
import android.os.Looper;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicBoolean;

final class NavigationApiClient {
    interface Callback {
        void onSuccess(JSONObject response);
        void onFailure(String failureClass, String detail);
    }

    private static final int MAX_RESPONSE_BYTES = 2_000_000;
    private static final int MAX_TRANSPORT_ATTEMPTS = 3;
    private final ExecutorService networkExecutor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final AtomicBoolean closed = new AtomicBoolean(false);

    void get(String baseUrl, String path, Callback callback) {
        request(baseUrl, path, "GET", null, callback);
    }

    void post(String baseUrl, String path, JSONObject payload, Callback callback) {
        request(baseUrl, path, "POST", payload, callback);
    }

    void close() {
        if (closed.compareAndSet(false, true)) {
            networkExecutor.shutdownNow();
        }
    }

    private void request(
            String baseUrl,
            String path,
            String method,
            JSONObject payload,
            Callback callback
    ) {
        if (closed.get()) {
            return;
        }
        try {
            networkExecutor.execute(
                    () -> requestWithRetries(baseUrl, path, method, payload, callback)
            );
        } catch (RejectedExecutionException error) {
            // AccessibilityService teardown can race a callback that wants to
            // post one final observation/session-stop request. Once closed,
            // dropping that lifecycle cleanup request is safer than crashing
            // and Android will not schedule further UI work for this client.
            if (!closed.get()) {
                fail(callback, "executor_rejected", error.getMessage());
            }
        }
    }

    private void requestWithRetries(
            String baseUrl,
            String path,
            String method,
            JSONObject payload,
            Callback callback
    ) {
        Exception lastError = null;
        for (int attempt = 1; attempt <= MAX_TRANSPORT_ATTEMPTS; attempt++) {
            try {
                requestOnce(baseUrl, path, method, payload, callback);
                return;
            } catch (Exception error) {
                lastError = error;
                if (attempt < MAX_TRANSPORT_ATTEMPTS) {
                    try {
                        Thread.sleep(500L * attempt);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        lastError = interrupted;
                        break;
                    }
                }
            }
        }
        Exception error = lastError == null ? new IOException("unknown transport error") : lastError;
        fail(callback, "transport_error", error.getClass().getSimpleName() + ": " + error.getMessage());
    }

    private void requestOnce(
            String baseUrl,
            String path,
            String method,
            JSONObject payload,
            Callback callback
    ) throws Exception {
        HttpURLConnection connection = null;
        try {
                URL url = new URL(stripTrailingSlash(baseUrl) + path);
                connection = (HttpURLConnection) url.openConnection();
                connection.setRequestMethod(method);
                connection.setConnectTimeout(8_000);
                // The remote planner may take longer than a local DB lookup. The server still enforces
                // its own planner timeout; the device must not abort a valid
                // bounded decision before that server-side deadline.
                connection.setReadTimeout(120_000);
                connection.setInstanceFollowRedirects(false);
                connection.setRequestProperty("Accept", "application/json");
                // ADB reverse + an SSH local forward can leave an HTTP/1.1
                // keep-alive response half-open after N100 has already sent
                // the complete body. Large /decide responses then wait for the
                // 120-second read timeout and are retried despite a server-side
                // 200. Close each bounded request explicitly and avoid content
                // encoding so completion is unambiguous across both tunnels.
                connection.setRequestProperty("Connection", "close");
                connection.setRequestProperty("Accept-Encoding", "identity");
                if (payload != null) {
                    byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
                    connection.setDoOutput(true);
                    connection.setFixedLengthStreamingMode(body.length);
                    connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                    try (OutputStream output = connection.getOutputStream()) {
                        output.write(body);
                    }
                }
                int status = connection.getResponseCode();
                InputStream stream = status >= 200 && status < 300
                        ? connection.getInputStream()
                        : connection.getErrorStream();
                String responseBody = readLimited(stream);
                if (status < 200 || status >= 300) {
                    fail(callback, "http_error", "HTTP " + status + ": " + responseBody);
                    return;
                }
                JSONObject response = new JSONObject(responseBody);
                if (!closed.get()) {
                    mainHandler.post(() -> {
                        if (!closed.get()) {
                            callback.onSuccess(response);
                        }
                    });
                }
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private void fail(Callback callback, String failureClass, String detail) {
        if (closed.get()) {
            return;
        }
        mainHandler.post(() -> {
            if (!closed.get()) {
                callback.onFailure(failureClass, detail == null ? "" : detail);
            }
        });
    }

    private static String readLimited(InputStream stream) throws IOException {
        if (stream == null) {
            return "";
        }
        try (InputStream input = stream; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8_192];
            int total = 0;
            int read;
            while ((read = input.read(buffer)) >= 0) {
                total += read;
                if (total > MAX_RESPONSE_BYTES) {
                    throw new IOException("Navigation API response exceeded size limit");
                }
                output.write(buffer, 0, read);
            }
            return output.toString(StandardCharsets.UTF_8.name());
        }
    }

    private static String stripTrailingSlash(String value) {
        String result = value.trim();
        while (result.endsWith("/")) {
            result = result.substring(0, result.length() - 1);
        }
        return result;
    }
}
