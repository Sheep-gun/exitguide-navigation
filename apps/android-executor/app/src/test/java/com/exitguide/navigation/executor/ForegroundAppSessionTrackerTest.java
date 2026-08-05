package com.exitguide.navigation.executor;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class ForegroundAppSessionTrackerTest {
    @Test
    public void launcherWaitsThenStartsTargetApp() {
        ForegroundAppSessionTracker tracker = new ForegroundAppSessionTracker();

        assertTrue(tracker.observe("com.sec.android.app.launcher").waitForAppChange);
        ForegroundAppSessionTracker.Observation target = tracker.observe("com.coupang.mobile");

        assertFalse(target.waitForAppChange);
        assertEquals("com.coupang.mobile", target.originAppPackage);
        assertEquals("com.coupang.mobile", target.currentAppPackage);
    }

    @Test
    public void expectedSystemHandoffKeepsOriginAndUpdatesCurrentApp() {
        ForegroundAppSessionTracker tracker = new ForegroundAppSessionTracker();
        tracker.observe("com.example.app");

        ForegroundAppSessionTracker.Observation handoff = tracker.observe("com.android.settings");

        assertFalse(handoff.startsNewSession);
        assertEquals("com.example.app", handoff.originAppPackage);
        assertEquals("com.android.settings", handoff.currentAppPackage);
        assertEquals("expected_handoff", handoff.transitionReason);
    }

    @Test
    public void unrelatedAppSwitchStartsNewSession() {
        ForegroundAppSessionTracker tracker = new ForegroundAppSessionTracker();
        tracker.observe("com.example.one");

        ForegroundAppSessionTracker.Observation switched = tracker.observe("com.example.two");

        assertTrue(switched.startsNewSession);
        assertEquals("com.example.two", switched.originAppPackage);
        assertEquals("com.example.one", switched.previousAppPackage);
        assertEquals("user_switch", switched.transitionReason);
    }

    @Test
    public void unsupportedAppMakesNextObservedAppANewSession() {
        ForegroundAppSessionTracker tracker = new ForegroundAppSessionTracker();
        tracker.observe("com.example.unsupported");
        tracker.markCurrentAppUnsupported();

        ForegroundAppSessionTracker.Observation switched = tracker.observe("com.example.target");

        assertTrue(switched.startsNewSession);
        assertEquals("com.example.target", switched.originAppPackage);
        assertEquals("com.example.target", switched.currentAppPackage);
    }
}
