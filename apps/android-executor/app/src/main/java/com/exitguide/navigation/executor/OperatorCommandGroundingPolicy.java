package com.exitguide.navigation.executor;

final class OperatorCommandGroundingPolicy {
    private OperatorCommandGroundingPolicy() {}

    static boolean accepts(
            String actionName,
            String expectedScreenFingerprint,
            String currentScreenFingerprint,
            boolean candidateStillGrounded
    ) {
        if (safe(expectedScreenFingerprint).equals(safe(currentScreenFingerprint))) {
            return true;
        }
        // Carousels, clocks and other unrelated regions may change between the Codex read and
        // command handling. A click remains grounded when the exact candidate_id still exists;
        // AccessibilityScreenReader.perform verifies the candidate's node fingerprint again at
        // execution time. Non-candidate actions retain strict whole-screen freshness.
        return "click".equals(safe(actionName)) && candidateStillGrounded;
    }

    private static String safe(String value) {
        return value == null ? "" : value.trim();
    }
}
