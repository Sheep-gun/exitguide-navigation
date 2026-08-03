package com.exitguide.navigation.executor;

final class DecisionDebounceWindow {
    private static final long NOT_STARTED = -1L;

    private final long maxDelayMs;
    private long startedAtMs = NOT_STARTED;

    DecisionDebounceWindow(long maxDelayMs) {
        if (maxDelayMs <= 0L) {
            throw new IllegalArgumentException("maxDelayMs must be positive");
        }
        this.maxDelayMs = maxDelayMs;
    }

    long boundedDelay(long nowMs, long requestedDelayMs) {
        if (requestedDelayMs < 0L) {
            throw new IllegalArgumentException("requestedDelayMs must not be negative");
        }
        if (startedAtMs == NOT_STARTED || nowMs < startedAtMs) {
            startedAtMs = nowMs;
        }
        long elapsedMs = nowMs - startedAtMs;
        long remainingMs = Math.max(0L, maxDelayMs - elapsedMs);
        return Math.min(requestedDelayMs, remainingMs);
    }

    void reset() {
        startedAtMs = NOT_STARTED;
    }
}
