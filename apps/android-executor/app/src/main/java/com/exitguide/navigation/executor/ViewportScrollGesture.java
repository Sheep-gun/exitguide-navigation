package com.exitguide.navigation.executor;

/**
 * Builds a deterministic 90% viewport swipe for the allowed scroll(direction) action.
 *
 * <p>The planner supplies only a direction. Coordinates are derived exclusively from the
 * current Accessibility root or scrollable-node bounds and are never accepted from a model.
 * A five-percent inset at each edge yields a ninety-percent traversal with approximately ten
 * percent overlap between consecutive screens.</p>
 */
final class ViewportScrollGesture {
    private static final float EDGE_INSET_RATIO = 0.05f;

    private ViewportScrollGesture() {
    }

    static final class Swipe {
        final float x;
        final float startY;
        final float endY;

        Swipe(float x, float startY, float endY) {
            this.x = x;
            this.startY = startY;
            this.endY = endY;
        }
    }

    static Swipe resolve(
            int left,
            int top,
            int right,
            int bottom,
            String direction
    ) {
        int width = Math.max(0, right - left);
        int height = Math.max(0, bottom - top);
        if (width == 0 || height == 0) {
            throw new IllegalArgumentException("scroll bounds must be non-empty");
        }
        float x = left + width / 2.0f;
        float upper = top + height * EDGE_INSET_RATIO;
        float lower = bottom - height * EDGE_INSET_RATIO;
        if ("down".equals(direction)) {
            return new Swipe(x, lower, upper);
        }
        if ("up".equals(direction)) {
            return new Swipe(x, upper, lower);
        }
        throw new IllegalArgumentException("direction must be up or down");
    }
}
