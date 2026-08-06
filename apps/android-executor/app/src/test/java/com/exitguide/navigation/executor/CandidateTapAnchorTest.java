package com.exitguide.navigation.executor;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public class CandidateTapAnchorTest {
    @Test
    public void wideShortSemanticProxyUsesTrailingAreaInLtr() {
        CandidateTapAnchor.TapPoint point = CandidateTapAnchor.resolve(
                300, 480, 750, 530, true, false
        );

        assertEquals(725.0f, point.x, 0.01f);
        assertEquals(505.0f, point.y, 0.01f);
    }

    @Test
    public void wideShortSemanticProxyUsesTrailingAreaInRtl() {
        CandidateTapAnchor.TapPoint point = CandidateTapAnchor.resolve(
                300, 480, 750, 530, true, true
        );

        assertEquals(325.0f, point.x, 0.01f);
        assertEquals(505.0f, point.y, 0.01f);
    }

    @Test
    public void regularSemanticProxyKeepsCenterAnchor() {
        CandidateTapAnchor.TapPoint point = CandidateTapAnchor.resolve(
                100, 100, 400, 300, true, false
        );

        assertEquals(250.0f, point.x, 0.01f);
        assertEquals(200.0f, point.y, 0.01f);
    }

    @Test
    public void directAccessibilityCandidateKeepsCenterAnchor() {
        CandidateTapAnchor.TapPoint point = CandidateTapAnchor.resolve(
                300, 480, 750, 530, false, false
        );

        assertEquals(525.0f, point.x, 0.01f);
        assertEquals(505.0f, point.y, 0.01f);
    }
}
