package com.exitguide.navigation.executor;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public final class DecisionDebounceWindowTest {
    @Test
    public void repeatedEventsCannotPostponeDecisionPastMaximum() {
        DecisionDebounceWindow window = new DecisionDebounceWindow(2_000L);

        assertEquals(700L, window.boundedDelay(10_000L, 700L));
        assertEquals(700L, window.boundedDelay(10_500L, 700L));
        assertEquals(500L, window.boundedDelay(11_500L, 700L));
        assertEquals(0L, window.boundedDelay(12_000L, 700L));
        assertEquals(0L, window.boundedDelay(12_500L, 700L));
    }

    @Test
    public void resetStartsIndependentDebounceWindow() {
        DecisionDebounceWindow window = new DecisionDebounceWindow(2_000L);
        window.boundedDelay(10_000L, 700L);
        window.reset();

        assertEquals(700L, window.boundedDelay(20_000L, 700L));
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsNonPositiveMaximum() {
        new DecisionDebounceWindow(0L);
    }
}
