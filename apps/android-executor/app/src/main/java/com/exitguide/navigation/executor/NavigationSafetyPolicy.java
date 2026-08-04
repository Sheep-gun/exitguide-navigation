package com.exitguide.navigation.executor;

import android.view.accessibility.AccessibilityNodeInfo;

import java.text.Normalizer;
import java.util.Locale;
import java.util.Set;

public final class NavigationSafetyPolicy {
    public static final Set<String> ALLOWED_ACTIONS = Set.of(
            "click",
            "scroll",
            "back",
            "wait_and_observe",
            "stop_for_user"
    );

    private static final String[] DANGEROUS_FINAL_PHRASES = {
            "탈퇴 확정",
            "최종 탈퇴",
            "영구 삭제",
            "삭제 확인",
            "해지 확정",
            "구독 해지 확인",
            "결제하기",
            "지금 결제",
            "구매하기",
            "개인정보 제출",
            "회원가입 완료",
            "가입 완료",
            "로그아웃",
            "계정 전환",
            "프로필 저장",
            "프로필 수정 완료",
            "프로필 삭제",
            "회원탈퇴",
            "회원 탈퇴",
            "계정 삭제",
            "계정을 삭제",
            "모두 동의하고",
            "동의하고 가입",
            "신청서 제출",
            "신청하기",
            "메시지 보내기",
            "전송하기",
            "장바구니 담기",
            "주문하기",
            "구독 확정",
            "구독 시작",
            "멤버십 가입 완료",
            "confirm deletion",
            "delete permanently",
            "confirm cancellation",
            "pay now",
            "purchase now",
            "submit personal information",
            "sign out",
            "switch account",
            "save profile",
            "delete profile",
            "delete account",
            "delete your account",
            "close account",
            "submit application",
            "send message",
            "add to cart",
            "place order",
            "start subscription"
    };

    private static final Set<String> STATE_CHANGING_ACTION_LABELS = Set.of(
            // Exact cancellation CTA labels are safety boundaries even when
            // the surrounding page has not yet exposed a separate confirm
            // dialog.  This keeps the Executor from entering an irreversible
            // cancellation flow merely because the label omits "확정".
            "멤버십 해지",
            "구독 해지",
            "구독 취소",
            "이용권 해지",
            "회원탈퇴",
            "회원 탈퇴",
            "계정 삭제",
            "google 계정 삭제",
            "cancel membership",
            "cancel subscription",
            "unsubscribe",
            "delete account",
            "delete your account",
            "close account",
            // Renewal/resubscription CTAs can immediately restore a paid
            // state. Keep these exact so "갱신일" remains read-only context.
            "갱신",
            "갱신하기",
            "지금 갱신",
            "멤버십 갱신",
            "멤버쉽 갱신",
            "구독 갱신",
            "재구독",
            "구독 재개",
            "멤버십 재개",
            "renew",
            "renew now",
            "renew membership",
            "renew subscription",
            "resubscribe",
            "resume membership",
            "resume subscription",
            "저장",
            "저장하기",
            "변경 저장",
            "변경 내용 저장",
            "변경사항 저장",
            "적용",
            "적용하기",
            "제출",
            "제출하기",
            "save",
            "save changes",
            "apply",
            "apply changes",
            "submit"
    );

    private static final Set<String> GENERIC_CANCELLATION_ACTION_LABELS = Set.of(
            "취소",
            "취소하기",
            "cancel"
    );

    private static final String[] MEMBERSHIP_CONTEXT_MARKERS = {
            "멤버십", "멤버쉽", "구독", "이용권",
            "membership", "subscription", "premium", "plan"
    };

    private static final String[] MEMBERSHIP_BILLING_OR_END_MARKERS = {
            "다음 결제", "결제일", "결제 수단", "혜택을 종료",
            "billing", "next payment", "payment method", "end benefit", "end membership"
    };

    private NavigationSafetyPolicy() {}

    public static boolean isAllowedAction(String action) {
        return ALLOWED_ACTIONS.contains(action);
    }

    public static String riskLevel(AccessibilityNodeInfo node, String semanticText) {
        String className = string(node.getClassName()).toLowerCase(Locale.ROOT);
        if (className.contains("switch")
                || className.contains("checkbox")
                || className.contains("radiobutton")
                || node.isCheckable()
                || node.isEditable()) {
            return "blocked";
        }
        if (isStateChangingActionLabel(preferredActionLabel(node))) {
            return "high";
        }
        return isDangerousFinalText(semanticText) ? "high" : "low";
    }

    public static boolean isDangerousFinalText(String value) {
        String normalized = normalize(value);
        for (String phrase : DANGEROUS_FINAL_PHRASES) {
            if (normalized.contains(normalize(phrase))) {
                return true;
            }
        }
        return false;
    }

    public static boolean isStateChangingActionLabel(String value) {
        return STATE_CHANGING_ACTION_LABELS.contains(normalize(value));
    }

    public static boolean isContextualMembershipCancellationAction(
            String label,
            String screenContext
    ) {
        if (!GENERIC_CANCELLATION_ACTION_LABELS.contains(normalize(label))) {
            return false;
        }
        String normalizedContext = normalize(screenContext);
        return containsAny(normalizedContext, MEMBERSHIP_CONTEXT_MARKERS)
                && containsAny(normalizedContext, MEMBERSHIP_BILLING_OR_END_MARKERS);
    }

    private static boolean containsAny(String value, String[] markers) {
        for (String marker : markers) {
            if (value.contains(normalize(marker))) {
                return true;
            }
        }
        return false;
    }

    static String normalize(String value) {
        return Normalizer.normalize(value == null ? "" : value, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT)
                .replaceAll("\\s+", " ")
                .trim();
    }

    private static String string(CharSequence value) {
        return value == null ? "" : value.toString();
    }

    private static String preferredActionLabel(AccessibilityNodeInfo node) {
        for (CharSequence value : new CharSequence[] {
                node.getText(), node.getContentDescription(), node.getHintText()
        }) {
            String candidate = string(value).trim();
            if (!candidate.isEmpty()) {
                return candidate;
            }
        }
        return "";
    }
}
