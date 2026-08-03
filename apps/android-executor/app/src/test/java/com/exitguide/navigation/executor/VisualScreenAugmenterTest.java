package com.exitguide.navigation.executor;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class VisualScreenAugmenterTest {
    @Test
    public void privacyClassifierMasksCredentialsAndPersonalIdentifiers() {
        assertTrue(VisualScreenAugmenter.isSensitiveText("person@example.com"));
        assertTrue(VisualScreenAugmenter.isSensitiveText("010-1234-5678"));
        assertTrue(VisualScreenAugmenter.isSensitiveText("프로필 @sample_user"));
        assertTrue(VisualScreenAugmenter.isSensitiveText("우*하 님"));
        assertTrue(VisualScreenAugmenter.isSensitiveText("총 312,717원"));
        assertTrue(VisualScreenAugmenter.isSensitiveText("인증번호 123456"));
        assertTrue(VisualScreenAugmenter.isSensitiveText("Bearer secret-value"));
        assertFalse(VisualScreenAugmenter.isSensitiveText("Premium 혜택"));
    }

    @Test
    public void recoverySignalsRequireVisualReinspection() throws Exception {
        assertTrue(ExitGuideAccessibilityService.requiresVisualRecovery(
                "no_change", "unchanged", ""
        ));
        assertTrue(ExitGuideAccessibilityService.requiresVisualRecovery(
                "navigated", "unknown", "back"
        ));
        assertFalse(ExitGuideAccessibilityService.requiresVisualRecovery(
                "navigated", "advanced", ""
        ));
    }
}
