package com.exitguide.navigation.executor;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

final class ForegroundAppSessionTracker {
    static final class Observation {
        final boolean waitForAppChange;
        final boolean startsNewSession;
        final String originAppPackage;
        final String currentAppPackage;
        final String previousAppPackage;
        final String transitionReason;

        Observation(
                boolean waitForAppChange,
                boolean startsNewSession,
                String originAppPackage,
                String currentAppPackage,
                String previousAppPackage,
                String transitionReason
        ) {
            this.waitForAppChange = waitForAppChange;
            this.startsNewSession = startsNewSession;
            this.originAppPackage = originAppPackage;
            this.currentAppPackage = currentAppPackage;
            this.previousAppPackage = previousAppPackage;
            this.transitionReason = transitionReason;
        }
    }

    private static final Set<String> SWITCH_SURFACES = new HashSet<>(Arrays.asList(
            "com.sec.android.app.launcher",
            "com.google.android.apps.nexuslauncher",
            "com.android.launcher3",
            "com.google.android.packageinstaller",
            "com.android.packageinstaller",
            "com.exitguide.navigation.executor"
    ));
    private static final Set<String> TRANSIENT_SURFACES = new HashSet<>(Arrays.asList(
            "com.android.systemui"
    ));
    private static final Set<String> EXPECTED_HANDOFF_PACKAGES = new HashSet<>(Arrays.asList(
            "com.android.settings",
            "com.android.chrome",
            "com.sec.android.app.sbrowser",
            "com.android.vending",
            "com.google.android.gms"
    ));

    private String originAppPackage = "";
    private String currentAppPackage = "";
    private boolean startNewSessionOnNextApp;

    Observation observe(String packageName) {
        String observed = safe(packageName);
        if (observed.isEmpty() || SWITCH_SURFACES.contains(observed)) {
            startNewSessionOnNextApp = true;
            return waiting(observed);
        }
        if (TRANSIENT_SURFACES.contains(observed)) {
            return waiting(observed);
        }

        String previous = currentAppPackage;
        if (originAppPackage.isEmpty() || startNewSessionOnNextApp) {
            boolean startsNew = !originAppPackage.isEmpty();
            originAppPackage = observed;
            currentAppPackage = observed;
            startNewSessionOnNextApp = false;
            return ready(startsNew, previous, startsNew ? "user_switch" : "unknown");
        }
        if (observed.equals(currentAppPackage)) {
            return ready(false, currentAppPackage, "unknown");
        }
        if (observed.equals(originAppPackage)
                || EXPECTED_HANDOFF_PACKAGES.contains(observed)) {
            currentAppPackage = observed;
            return ready(false, previous, "expected_handoff");
        }

        originAppPackage = observed;
        currentAppPackage = observed;
        return ready(true, previous, "user_switch");
    }

    void markCurrentAppUnsupported() {
        startNewSessionOnNextApp = true;
    }

    void reset() {
        originAppPackage = "";
        currentAppPackage = "";
        startNewSessionOnNextApp = false;
    }

    private Observation waiting(String observed) {
        return new Observation(
                true,
                false,
                originAppPackage,
                observed,
                currentAppPackage,
                "system_interstitial"
        );
    }

    private Observation ready(boolean startsNew, String previous, String reason) {
        return new Observation(
                false,
                startsNew,
                originAppPackage,
                currentAppPackage,
                previous,
                reason
        );
    }

    private static String safe(String value) {
        return value == null ? "" : value.trim();
    }
}
