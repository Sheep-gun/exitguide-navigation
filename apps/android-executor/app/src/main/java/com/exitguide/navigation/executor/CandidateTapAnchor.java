package com.exitguide.navigation.executor;

/**
 * Resolves a tap point strictly inside the bounds of an Accessibility-grounded candidate.
 *
 * <p>Some Compose rows expose a non-clickable semantic button whose bounds contain a text
 * label and a trailing action icon, while omitting the icon as a separate Accessibility node.
 * Tapping the geometric centre then lands on the inert label. For a wide, short proxy only,
 * prefer the conventional trailing action area. This never accepts coordinates from a model
 * and never leaves the current candidate's Accessibility bounds.</p>
 */
final class CandidateTapAnchor {
    private static final float WIDE_SHORT_ASPECT_RATIO = 4.0f;

    private CandidateTapAnchor() {
    }

    static final class TapPoint {
        final float x;
        final float y;

        TapPoint(float x, float y) {
            this.x = x;
            this.y = y;
        }
    }

    static TapPoint resolve(
            int left,
            int top,
            int right,
            int bottom,
            boolean semanticProxy,
            boolean rightToLeft
    ) {
        int width = Math.max(0, right - left);
        int height = Math.max(0, bottom - top);
        float x = (left + right) / 2.0f;
        float y = (top + bottom) / 2.0f;
        if (!semanticProxy
                || width == 0
                || height == 0
                || width < height * WIDE_SHORT_ASPECT_RATIO) {
            return new TapPoint(x, y);
        }
        // A trailing icon normally occupies a square whose side is the row height. Its centre is
        // therefore half a row height inside the trailing edge.
        float inset = height / 2.0f;
        inset = Math.min(inset, Math.max(1.0f, width / 2.0f - 1.0f));
        x = rightToLeft ? left + inset : right - inset;
        return new TapPoint(x, y);
    }
}
