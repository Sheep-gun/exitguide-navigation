package com.exitguide.navigation.executor;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public class AccessibilityScreenReaderContractTest {
    @Test
    public void completeTraversalPreservesObservedTotal() {
        assertEquals(77, AccessibilityScreenReader.reportedNodesTotal(77, 77, false));
    }

    @Test
    public void depthTruncationReportsAtLeastOneOmittedNode() {
        assertEquals(78, AccessibilityScreenReader.reportedNodesTotal(77, 77, true));
    }

    @Test
    public void nodeLimitTruncationPreservesLargerTraversedTotal() {
        assertEquals(620, AccessibilityScreenReader.reportedNodesTotal(620, 500, true));
    }
}
