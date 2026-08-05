package com.exitguide.navigation.executor;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotEquals;

import java.util.Arrays;

import org.junit.Test;

public final class StableScreenIdentityTest {
    @Test
    public void countdownChangesDoNotResumePausedCollector() {
        String first = StableScreenIdentity.fingerprint(
                "com.coupang.mobile",
                "쿠팡",
                "android.widget.TextView",
                Arrays.asList("버튼|와우 멤버십", "버튼|장바구니 4 08:06:31")
        );
        String second = StableScreenIdentity.fingerprint(
                "com.coupang.mobile",
                "쿠팡",
                "android.widget.TextView",
                Arrays.asList("버튼|와우 멤버십", "버튼|장바구니 4 08:05:41")
        );

        assertEquals(first, second);
    }

    @Test
    public void meaningfulCandidateChangeResumesPausedCollector() {
        String membership = StableScreenIdentity.fingerprint(
                "com.coupang.mobile",
                "쿠팡",
                "android.widget.TextView",
                Arrays.asList("버튼|와우 멤버십", "버튼|장바구니 4 08:06:31")
        );
        String cancellation = StableScreenIdentity.fingerprint(
                "com.coupang.mobile",
                "쿠팡",
                "android.widget.TextView",
                Arrays.asList("버튼|해지 안내", "버튼|장바구니 4 08:06:31")
        );

        assertNotEquals(membership, cancellation);
    }
}
