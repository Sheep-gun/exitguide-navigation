package com.exitguide.navigation.executor;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class ViewportScrollPlanTest {
    @Test
    public void downScrollMovesThroughNinetyPercentOfVisibleViewport() {
        ViewportScrollPlan plan = ViewportScrollPlan.create(
                0, 100, 1080, 2300, 1080, 2400, false
        );

        assertNotNull(plan);
        assertEquals(0.90f, plan.viewportFraction, 0.0001f);
        assertTrue(plan.startY > plan.endY);
        assertEquals(1080f / 2f, plan.startX, 0.0001f);
    }

    @Test
    public void upScrollUsesSameDistanceInReverse() {
        ViewportScrollPlan down = ViewportScrollPlan.create(
                0, 100, 1080, 2300, 1080, 2400, false
        );
        ViewportScrollPlan up = ViewportScrollPlan.create(
                0, 100, 1080, 2300, 1080, 2400, true
        );

        assertNotNull(down);
        assertNotNull(up);
        assertEquals(down.startY, up.endY, 0.0001f);
        assertEquals(down.endY, up.startY, 0.0001f);
        assertEquals(0.90f, up.viewportFraction, 0.0001f);
    }

    @Test
    public void clipsScrollableBoundsToPhysicalDisplay() {
        ViewportScrollPlan plan = ViewportScrollPlan.create(
                -50, -200, 1200, 2800, 1080, 2400, false
        );

        assertNotNull(plan);
        assertEquals(540f, plan.startX, 0.0001f);
        assertEquals(0.90f, plan.viewportFraction, 0.0001f);
        assertTrue(plan.startY <= 2400f);
        assertTrue(plan.endY >= 0f);
    }

    @Test
    public void rejectsDegenerateViewport() {
        assertNull(ViewportScrollPlan.create(0, 0, 100, 10, 1080, 2400, false));
    }
}
