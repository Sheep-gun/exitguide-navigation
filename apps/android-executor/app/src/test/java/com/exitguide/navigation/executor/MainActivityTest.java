package com.exitguide.navigation.executor;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class MainActivityTest {
    private static final String PACKAGE = "com.exitguide.navigation.executor";
    private static final String SERVICE = PACKAGE + ".ExitGuideAccessibilityService";

    @Test
    public void matchesFullRelativeAndSimpleServiceNames() {
        assertTrue(MainActivity.matchesAccessibilityService(PACKAGE, SERVICE, PACKAGE, SERVICE));
        assertTrue(MainActivity.matchesAccessibilityService(
                PACKAGE, SERVICE, PACKAGE, ".ExitGuideAccessibilityService"
        ));
        assertTrue(MainActivity.matchesAccessibilityService(
                PACKAGE, SERVICE, PACKAGE, "ExitGuideAccessibilityService"
        ));
    }

    @Test
    public void rejectsOtherPackagesAndClasses() {
        assertFalse(MainActivity.matchesAccessibilityService(
                PACKAGE, SERVICE, "com.exitguide.ai", ".ExitGuideAccessibilityService"
        ));
        assertFalse(MainActivity.matchesAccessibilityService(
                PACKAGE, SERVICE, PACKAGE, ".OtherAccessibilityService"
        ));
        assertFalse(MainActivity.matchesAccessibilityService(
                PACKAGE, SERVICE, PACKAGE, null
        ));
    }

    @Test
    public void readsExactServiceFromSecureSettingFallback() {
        String enabled = "com.openai.chatgpt/.ScreenService:"
                + PACKAGE + "/.ExitGuideAccessibilityService";
        assertTrue(MainActivity.enabledSettingContains(PACKAGE, SERVICE, enabled));
        assertFalse(MainActivity.enabledSettingContains(
                PACKAGE,
                SERVICE,
                "com.exitguide.ai/.ExitGuideAccessibilityService"
        ));
        assertFalse(MainActivity.enabledSettingContains(PACKAGE, SERVICE, null));
    }
}
