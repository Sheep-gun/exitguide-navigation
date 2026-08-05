package com.exitguide.navigation.executor;

final class CollectorContinuationGate {
    private boolean waitingForUser;
    private String pausedAppPackage = "";
    private String pausedScreenFingerprint = "";
    private boolean requireAppChange;

    void awaitUserScreenChange(String appPackage, String screenFingerprint) {
        waitingForUser = true;
        pausedAppPackage = safe(appPackage);
        pausedScreenFingerprint = safe(screenFingerprint);
        requireAppChange = false;
    }

    void awaitAppChange(String appPackage) {
        waitingForUser = true;
        pausedAppPackage = safe(appPackage);
        pausedScreenFingerprint = "";
        requireAppChange = true;
    }

    boolean consumeIfScreenChanged(String appPackage, String screenFingerprint) {
        if (!waitingForUser) {
            return false;
        }
        String currentPackage = safe(appPackage);
        String currentFingerprint = safe(screenFingerprint);
        if (requireAppChange && pausedAppPackage.equals(currentPackage)) {
            return false;
        }
        if (pausedAppPackage.equals(currentPackage)
                && pausedScreenFingerprint.equals(currentFingerprint)) {
            return false;
        }
        reset();
        return true;
    }

    boolean isWaitingForUser() {
        return waitingForUser;
    }

    void reset() {
        waitingForUser = false;
        pausedAppPackage = "";
        pausedScreenFingerprint = "";
        requireAppChange = false;
    }

    private static String safe(String value) {
        return value == null ? "" : value;
    }
}
