package com.exitguide.navigation.executor;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class AdbConnectionLeaseTest {
    @Test
    public void acceptsHeartbeatAtTimeoutBoundary() {
        long heartbeat = 1_000_000L;
        assertTrue(AdbConnectionLease.isFresh(
                heartbeat + AdbConnectionLease.TIMEOUT_MS,
                heartbeat
        ));
        assertEquals(1L, AdbConnectionLease.millisecondsUntilExpired(
                heartbeat + AdbConnectionLease.TIMEOUT_MS,
                heartbeat
        ));
    }

    @Test
    public void rejectsMissingExpiredAndFutureHeartbeat() {
        long now = 1_000_000L;
        assertFalse(AdbConnectionLease.isFresh(now, 0L));
        assertFalse(AdbConnectionLease.isFresh(
                now,
                now - AdbConnectionLease.TIMEOUT_MS - 1L
        ));
        assertFalse(AdbConnectionLease.isFresh(now, now + 1L));
        assertEquals(0L, AdbConnectionLease.millisecondsUntilExpired(now, 0L));
    }
}
