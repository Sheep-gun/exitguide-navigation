package com.exitguide.navigation.executor;

/** Pure lease policy shared by the ADB collector receiver and executor. */
final class AdbConnectionLease {
    static final long TIMEOUT_MS = 15_000L;
    static final int ACCEPTED_RESULT_CODE = 73;

    private AdbConnectionLease() {}

    static boolean isFresh(long nowEpochMillis, long lastHeartbeatEpochMillis) {
        if (lastHeartbeatEpochMillis <= 0L || nowEpochMillis < lastHeartbeatEpochMillis) {
            return false;
        }
        return nowEpochMillis - lastHeartbeatEpochMillis <= TIMEOUT_MS;
    }

    static long millisecondsUntilExpired(long nowEpochMillis, long lastHeartbeatEpochMillis) {
        if (!isFresh(nowEpochMillis, lastHeartbeatEpochMillis)) {
            return 0L;
        }
        // isFresh includes the exact timeout boundary, so one millisecond is
        // still left at that point.
        return TIMEOUT_MS - (nowEpochMillis - lastHeartbeatEpochMillis) + 1L;
    }
}
