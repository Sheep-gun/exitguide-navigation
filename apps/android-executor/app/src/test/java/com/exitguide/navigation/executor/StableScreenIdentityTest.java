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

    @Test
    public void koreanRelativeCountdownDoesNotInvalidateOperatorCommand() {
        String first = StableScreenIdentity.fingerprint(
                "com.sampleapp",
                "배달의민족",
                "android.view.View",
                Arrays.asList(
                        "button|마이배민",
                        "button|15분 뒤면 사라질 5,000원 할인 14분 49초 후에 사라져요"
                )
        );
        String second = StableScreenIdentity.fingerprint(
                "com.sampleapp",
                "배달의민족",
                "android.view.View",
                Arrays.asList(
                        "button|마이배민",
                        "button|15분 뒤면 사라질 5,000원 할인 14분 47초 후에 사라져요"
                )
        );

        assertEquals(first, second);
    }
}
