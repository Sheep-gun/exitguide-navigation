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
            "submit application",
            "send message",
            "add to cart",
            "place order",
            "start subscription"
    };

    private static final Set<String> STATE_CHANGING_ACTION_LABELS = Set.of(
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
        if (isStateChangingActionLabel(string(node.getText()))
                || isStateChangingActionLabel(string(node.getContentDescription()))) {
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

    static String normalize(String value) {
        return Normalizer.normalize(value == null ? "" : value, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT)
                .replaceAll("\\s+", " ")
                .trim();
    }

    private static String string(CharSequence value) {
        return value == null ? "" : value.toString();
    }
}
