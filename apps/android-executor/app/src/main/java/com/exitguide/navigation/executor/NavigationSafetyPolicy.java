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
            "confirm deletion",
            "delete permanently",
            "confirm cancellation",
            "pay now",
            "purchase now",
            "submit personal information"
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
                || node.isEditable()) {
            return "blocked";
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
