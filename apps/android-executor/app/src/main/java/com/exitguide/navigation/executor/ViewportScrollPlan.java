package com.exitguide.navigation.executor;

/**
 * Deterministic, screen-grounded geometry for one allowed scroll(direction).
 *
 * <p>The model never supplies coordinates. The Executor derives a swipe from
 * the Accessibility-confirmed scrollable viewport and moves through 90% of
 * its visible height, leaving only about 10% overlap for visual continuity.</p>
 */
final class ViewportScrollPlan {
    static final float VIEWPORT_FRACTION = 0.90f;

    final float startX;
    final float startY;
    final float endX;
    final float endY;
    final float viewportFraction;

    private ViewportScrollPlan(
            float startX,
            float startY,
            float endX,
            float endY,
            float viewportFraction
    ) {
        this.startX = startX;
        this.startY = startY;
        this.endX = endX;
        this.endY = endY;
        this.viewportFraction = viewportFraction;
    }

    static ViewportScrollPlan create(
            int left,
            int top,
            int right,
            int bottom,
            int displayWidth,
            int displayHeight,
            boolean scrollUp
    ) {
        if (displayWidth <= 0 || displayHeight <= 0) {
            return null;
        }
        int clippedLeft = clamp(left, 0, displayWidth - 1);
        int clippedTop = clamp(top, 0, displayHeight - 1);
        int clippedRight = clamp(right, clippedLeft + 1, displayWidth);
        int clippedBottom = clamp(bottom, clippedTop + 1, displayHeight);
        int height = clippedBottom - clippedTop;
        if (height < 20) {
            return null;
        }

        float overlapPerEdge = (1.0f - VIEWPORT_FRACTION) / 2.0f;
        float lowY = clippedTop + (height * overlapPerEdge);
        float highY = clippedBottom - (height * overlapPerEdge);
        float centerX = clippedLeft + ((clippedRight - clippedLeft) / 2.0f);
        float actualFraction = Math.abs(highY - lowY) / height;
        return scrollUp
                ? new ViewportScrollPlan(centerX, lowY, centerX, highY, actualFraction)
                : new ViewportScrollPlan(centerX, highY, centerX, lowY, actualFraction);
    }

    private static int clamp(int value, int minimum, int maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }
}
