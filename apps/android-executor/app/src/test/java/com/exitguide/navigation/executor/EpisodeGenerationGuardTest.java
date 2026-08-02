package com.exitguide.navigation.executor;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class EpisodeGenerationGuardTest {
    @Test
    public void rejectsStoppedAndSupersededCallbacks() {
        EpisodeGenerationGuard guard = new EpisodeGenerationGuard();
        long first = guard.reset();
        assertTrue(guard.accepts(first, true));
        assertFalse(guard.accepts(first, false));

        long second = guard.reset();
        assertFalse(guard.accepts(first, true));
        assertTrue(guard.accepts(second, true));
    }
}
