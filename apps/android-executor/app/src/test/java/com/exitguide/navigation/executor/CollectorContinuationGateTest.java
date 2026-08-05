package com.exitguide.navigation.executor;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class CollectorContinuationGateTest {
    @Test
    public void sameScreenKeepsWaiting() {
        CollectorContinuationGate gate = new CollectorContinuationGate();
        gate.awaitUserScreenChange("com.example", "screen-a");

        assertFalse(gate.consumeIfScreenChanged("com.example", "screen-a"));
        assertTrue(gate.isWaitingForUser());
    }

    @Test
    public void changedScreenResumesExactlyOnce() {
        CollectorContinuationGate gate = new CollectorContinuationGate();
        gate.awaitUserScreenChange("com.example", "screen-a");

        assertTrue(gate.consumeIfScreenChanged("com.example", "screen-b"));
        assertFalse(gate.isWaitingForUser());
        assertFalse(gate.consumeIfScreenChanged("com.example", "screen-c"));
    }

    @Test
    public void changedAppResumes() {
        CollectorContinuationGate gate = new CollectorContinuationGate();
        gate.awaitUserScreenChange("com.example.one", "screen-a");

        assertTrue(gate.consumeIfScreenChanged("com.example.two", "screen-a"));
    }

    @Test
    public void firstReadableScreenResumesAfterMissingSnapshot() {
        CollectorContinuationGate gate = new CollectorContinuationGate();
        gate.awaitUserScreenChange("", "");

        assertTrue(gate.consumeIfScreenChanged("com.example", "screen-a"));
    }

    @Test
    public void appWaitIgnoresDynamicChangesInsideSameLauncher() {
        CollectorContinuationGate gate = new CollectorContinuationGate();
        gate.awaitAppChange("com.example.launcher");

        assertFalse(gate.consumeIfScreenChanged("com.example.launcher", "screen-b"));
        assertTrue(gate.consumeIfScreenChanged("com.example.target", "screen-c"));
    }
}
