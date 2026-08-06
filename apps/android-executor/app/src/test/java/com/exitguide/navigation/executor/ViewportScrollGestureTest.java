package com.exitguide.navigation.executor;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertThrows;

import org.junit.Test;

public final class ViewportScrollGestureTest {
    @Test
    public void downScrollMovesFingerUpAcrossNinetyPercentOfBounds() {
        ViewportScrollGesture.Swipe swipe = ViewportScrollGesture.resolve(
                100, 200, 1100, 2200, "down"
        );

        assertEquals(600.0f, swipe.x, 0.01f);
        assertEquals(2100.0f, swipe.startY, 0.01f);
        assertEquals(300.0f, swipe.endY, 0.01f);
        assertEquals(1800.0f, swipe.startY - swipe.endY, 0.01f);
    }

    @Test
    public void upScrollMovesFingerDownAcrossNinetyPercentOfBounds() {
        ViewportScrollGesture.Swipe swipe = ViewportScrollGesture.resolve(
                100, 200, 1100, 2200, "up"
        );

        assertEquals(600.0f, swipe.x, 0.01f);
        assertEquals(300.0f, swipe.startY, 0.01f);
        assertEquals(2100.0f, swipe.endY, 0.01f);
    }

    @Test
    public void invalidBoundsAreRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> ViewportScrollGesture.resolve(0, 0, 0, 100, "down")
        );
    }
}
