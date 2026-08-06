package com.exitguide.navigation.executor;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class OperatorCommandGroundingPolicyTest {
    @Test
    public void exactScreenFingerprintAcceptsAnyAllowedAction() {
        assertTrue(OperatorCommandGroundingPolicy.accepts("back", "screen-a", "screen-a", false));
    }

    @Test
    public void carouselChangeKeepsExactCandidateClickGrounded() {
        assertTrue(OperatorCommandGroundingPolicy.accepts("click", "screen-a", "screen-b", true));
    }

    @Test
    public void changedScreenRejectsMissingCandidateClick() {
        assertFalse(OperatorCommandGroundingPolicy.accepts("click", "screen-a", "screen-b", false));
    }

    @Test
    public void changedScreenRejectsNonCandidateAction() {
        assertFalse(OperatorCommandGroundingPolicy.accepts("scroll", "screen-a", "screen-b", true));
    }
}
