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
        assertTrue(NavigationSafetyPolicy.isDangerousFinalText("프로필 삭제"));
        assertTrue(NavigationSafetyPolicy.isDangerousFinalText("Delete profile"));
        assertTrue(NavigationSafetyPolicy.isDangerousFinalText("Start subscription"));
        assertFalse(NavigationSafetyPolicy.isDangerousFinalText("로그아웃"));
        assertFalse(NavigationSafetyPolicy.isDangerousFinalText("회원탈퇴 메뉴"));
        assertFalse(NavigationSafetyPolicy.isDangerousFinalText("장바구니 담기"));
        assertFalse(NavigationSafetyPolicy.isDangerousFinalText("마이페이지"));
        assertFalse(NavigationSafetyPolicy.isDangerousFinalText("멤버십 관리"));
    }

    @Test
    public void onlyFinalCommitLabelsAreBlockedWithoutSubstringOverreach() {
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("멤버십 해지"));
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("Cancel subscription"));
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("Unsubscribe"));
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("Google 계정 삭제"));
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("Delete account"));
        assertTrue(NavigationSafetyPolicy.isStateChangingActionLabel("탈퇴 확정"));
        assertTrue(NavigationSafetyPolicy.isStateChangingActionLabel("Confirm deletion"));
        assertTrue(NavigationSafetyPolicy.isStateChangingActionLabel("갱신"));
        assertTrue(NavigationSafetyPolicy.isStateChangingActionLabel("Renew subscription"));
        assertTrue(NavigationSafetyPolicy.isStateChangingActionLabel("Resubscribe"));
        assertTrue(NavigationSafetyPolicy.isStateChangingActionLabel("저장하기"));
        assertTrue(NavigationSafetyPolicy.isStateChangingActionLabel(" Save Changes "));
        assertTrue(NavigationSafetyPolicy.isStateChangingActionLabel("적용"));
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("저장된 결제수단"));
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("변경 내역"));
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("멤버십 관리"));
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("해지 안내"));
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("갱신일: 9월 3일"));
        assertFalse(NavigationSafetyPolicy.isStateChangingActionLabel("멤버십 갱신 안내"));
    }

    @Test
    public void destructiveNavigationRequiresFinalConfirmationContext() {
        assertTrue(NavigationSafetyPolicy.isContextualMembershipCancellationAction(
                "회원탈퇴",
                "정말 탈퇴하시겠습니까? 모든 데이터는 삭제됩니다."
        ));
        assertTrue(NavigationSafetyPolicy.isContextualMembershipCancellationAction(
                "Delete account",
                "Are you sure? This cannot be undone."
        ));
        assertFalse(NavigationSafetyPolicy.isContextualMembershipCancellationAction(
                "회원탈퇴",
                "회원정보 화면의 회원탈퇴 메뉴"
        ));
        assertFalse(NavigationSafetyPolicy.isContextualMembershipCancellationAction(
                "취소",
                "정말 알림을 닫으시겠습니까?"
        ));
        assertTrue(NavigationSafetyPolicy.isContextualMembershipCancellationAction(
                "해지하기",
                "배민클럽 이용 중 다음 결제일 2026년 9월 1일"
        ));
        assertFalse(NavigationSafetyPolicy.isContextualMembershipCancellationAction(
                "해지하기",
                "알림 해지하기"
        ));
    }
}
