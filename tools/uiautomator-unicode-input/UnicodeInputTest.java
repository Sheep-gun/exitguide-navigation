package com.exitguide.tools;

import android.os.Bundle;
import android.os.SystemClock;
import android.util.Base64;
import android.view.accessibility.AccessibilityNodeInfo;

import com.android.uiautomator.core.UiObject;
import com.android.uiautomator.core.UiSelector;
import com.android.uiautomator.testrunner.UiAutomatorTestCase;

import java.nio.charset.StandardCharsets;

/** Shell-only UIAutomator helper for setting one Unicode text field in E2E tests. */
public final class UnicodeInputTest extends UiAutomatorTestCase {
    public void testSetText() throws Exception {
        Bundle params = getParams();
        String encodedText = require(params, "textB64");
        String packageName = require(params, "packageName");
        String className = params.getString("className", "android.widget.EditText");
        int instance = Integer.parseInt(params.getString("instance", "0"));
        String text = new String(Base64.decode(encodedText, Base64.DEFAULT), StandardCharsets.UTF_8);

        UnicodeUiObject field = new UnicodeUiObject(
            new UiSelector()
                .packageName(packageName)
                .className(className)
                .instance(instance)
        );
        assertTrue("Target Unicode input field was not visible", field.waitForExists(5_000));
        AccessibilityNodeInfo node = field.accessibilityNode(5_000);
        assertNotNull("Target Unicode accessibility node was not available", node);
        Bundle arguments = new Bundle();
        arguments.putCharSequence(
            AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
            text
        );
        assertTrue(
            "Accessibility ACTION_SET_TEXT could not set the Unicode input text",
            node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)
        );
        SystemClock.sleep(300);
        assertEquals("Unicode input verification failed", text, field.getText());
    }

    private static String require(Bundle params, String key) {
        String value = params.getString(key, "");
        if (value == null || value.isEmpty()) {
            throw new IllegalArgumentException("Missing UIAutomator parameter: " + key);
        }
        return value;
    }

    private static final class UnicodeUiObject extends UiObject {
        UnicodeUiObject(UiSelector selector) {
            super(selector);
        }

        AccessibilityNodeInfo accessibilityNode(long timeoutMillis) {
            return findAccessibilityNodeInfo(timeoutMillis);
        }
    }
}
