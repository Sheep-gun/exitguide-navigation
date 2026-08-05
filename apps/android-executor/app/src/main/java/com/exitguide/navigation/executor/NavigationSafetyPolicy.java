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
            "탈퇴를 확정",
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
            "프로필 저장",
            "프로필 수정 완료",
            "프로필 삭제",
            "모두 동의하고",
            "동의하고 가입",
            "신청서 제출",
            "신청하기",
            "메시지 보내기",
            "전송하기",
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
            "save profile",
            "delete profile",
            "submit application",
            "send message",
            "place order",
            "start subscription"
    };

    private static final Set<String> IRREVERSIBLE_EXACT_LABELS = Set.of(
            "탈퇴 확정",
            "최종 탈퇴",
            "영구 삭제",
            "삭제 확인",
            "해지 확정",
            "결제하기",
            "지금 결제",
            "구매하기",
            "주문하기",
            "회원가입 완료",
            "가입 완료",
            "동의하고 가입",
            "모두 동의하고",
            "전송하기",
            "메시지 보내기",
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
            "프로필 저장",
            "프로필 삭제",
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
            "submit",
            "confirm deletion",
            "delete permanently",
            "confirm cancellation",
            "pay now",
            "purchase now",
            "place order",
            "start subscription",
            "send message"
    );

    private static final Set<String> DESTRUCTIVE_FLOW_LABELS = Set.of(
            "멤버십 해지", "구독 해지", "구독 취소", "이용권 해지",
            "회원탈퇴", "회원 탈퇴", "탈퇴하기", "계정 삭제", "google 계정 삭제",
            "cancel membership", "cancel subscription", "unsubscribe",
            "delete account", "delete your account", "close account"
    );

    private static final String[] FINAL_CONFIRMATION_MARKERS = {
            "정말", "확정", "최종", "즉시", "영구", "복구할 수 없", "되돌릴 수 없",
            "삭제됩니다", "탈퇴됩니다", "종료됩니다", "혜택이 종료", "모든 데이터",
            "are you sure", "confirm", "permanent", "cannot be undone", "will be deleted"
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
        if (isIrreversibleFinalAction(preferredActionLabel(node), semanticText)) {
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
        return IRREVERSIBLE_EXACT_LABELS.contains(normalize(value));
    }

    public static boolean isContextualMembershipCancellationAction(
            String label,
            String screenContext
    ) {
        return isIrreversibleFinalAction(label, screenContext);
    }

    public static boolean isIrreversibleFinalAction(String label, String screenContext) {
        String normalizedLabel = normalize(label);
        if (IRREVERSIBLE_EXACT_LABELS.contains(normalizedLabel)) {
            return true;
        }
        return DESTRUCTIVE_FLOW_LABELS.contains(normalizedLabel)
                && containsAny(normalize(screenContext), FINAL_CONFIRMATION_MARKERS);
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
