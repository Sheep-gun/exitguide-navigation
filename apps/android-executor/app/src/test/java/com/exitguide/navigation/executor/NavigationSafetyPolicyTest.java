package com.exitguide.navigation.executor;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class NavigationSafetyPolicyTest {
    @Test
    public void onlyProtocolActionsAreAllowed() {
        assertTrue(NavigationSafetyPolicy.isAllowedAction("click"));
        assertTrue(NavigationSafetyPolicy.isAllowedAction("scroll"));
        assertTrue(NavigationSafetyPolicy.isAllowedAction("back"));
        assertTrue(NavigationSafetyPolicy.isAllowedAction("wait_and_observe"));
        assertTrue(NavigationSafetyPolicy.isAllowedAction("stop_for_user"));
        assertFalse(NavigationSafetyPolicy.isAllowedAction("tap_coordinate"));
        assertFalse(NavigationSafetyPolicy.isAllowedAction("type_text"));
    }

    @Test
    public void dangerousFinalTextIsBlocked() {
        assertTrue(NavigationSafetyPolicy.isDangerousFinalText("정말로 탈퇴 확정"));
        assertTrue(NavigationSafetyPolicy.isDangerousFinalText("지금 결제하기"));
        assertTrue(NavigationSafetyPolicy.isDangerousFinalText("회원가입 완료"));
        assertTrue(NavigationSafetyPolicy.isDangerousFinalText("Confirm cancellation"));
        assertTrue(NavigationSafetyPolicy.isDangerousFinalText("로그아웃"));
        assertTrue(NavigationSafetyPolicy.isDangerousFinalText("장바구니 담기"));
        assertTrue(NavigationSafetyPolicy.isDangerousFinalText("Start subscription"));
        assertFalse(NavigationSafetyPolicy.isDangerousFinalText("마이페이지"));
        assertFalse(NavigationSafetyPolicy.isDangerousFinalText("멤버십 관리"));
    }

    @Test
    public void stateChangingActionLabelsAreBlockedWithoutSubstringOverreach() {
        assertTrue(NavigationSafetyPolicy.isStateChangingActionLabel("저장하기"));
        assertTrue(NavigationSafetyPolicy.isStateChangingActionLabel(" Save Changes "));
        assertTrue(NavigationSafetyPolicy.isStateChangingActionLabel("적용"));
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("저장된 결제수단"));
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("변경 내역"));
    }
}
