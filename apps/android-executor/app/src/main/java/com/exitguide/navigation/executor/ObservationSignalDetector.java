package com.exitguide.navigation.executor;

import java.text.Normalizer;
import java.util.Locale;

final class ObservationSignalDetector {
    private ObservationSignalDetector() {}

    static String detect(
            String executionSignal,
            String beforePackage,
            String afterPackage,
            String screenSemantics
    ) {
        if (executionSignal != null && !"none".equals(executionSignal)) {
            return executionSignal;
        }
        String text = normalize(screenSemantics);
        if (containsAny(text,
                "생체 인증", "생체인증", "지문을 입력", "지문 인증", "biometric",
                "fingerprint authentication", "fingerprint scanner")) {
            return "blocked";
        }
        if (beforePackage != null
                && !beforePackage.isEmpty()
                && afterPackage != null
                && !afterPackage.isEmpty()
                && !beforePackage.equals(afterPackage)) {
            return "external_app";
        }
        if (containsAny(text,
                "네트워크 오류", "연결할 수 없습니다", "다시 시도", "network error",
                "connection failed", "offline")) {
            return "network_error";
        }
        if (containsAny(text,
                "로그인이 필요", "로그인 후", "계속하려면 로그인", "login required",
                "sign in to continue")) {
            return "login_required";
        }
        return "none";
    }

    private static boolean containsAny(String value, String... phrases) {
        for (String phrase : phrases) {
            if (value.contains(normalize(phrase))) {
                return true;
            }
        }
        return false;
    }

    private static String normalize(String value) {
        return Normalizer.normalize(value == null ? "" : value, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT)
                .replaceAll("\\s+", " ")
                .trim();
    }
}
