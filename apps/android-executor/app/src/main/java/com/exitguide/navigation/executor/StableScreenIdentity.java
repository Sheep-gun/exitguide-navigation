package com.exitguide.navigation.executor;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

final class StableScreenIdentity {
    private static final Pattern VOLATILE_CLOCK_PATTERN = Pattern.compile(
            "(?<!\\d)(?:\\d{1,3}:)?[0-5]?\\d:[0-5]\\d(?!\\d)"
    );
    private static final Pattern VOLATILE_KOREAN_DURATION_PATTERN = Pattern.compile(
            "(?<!\\d)\\d+\\s*분(?:\\s*\\d+\\s*초)?(?!\\d)|(?<!\\d)\\d+\\s*초(?!\\d)"
    );

    private StableScreenIdentity() {
    }

    static String fingerprint(
            String appPackage,
            String title,
            String accessibilityRootClass,
            List<String> candidateSignatures
    ) {
        StringBuilder value = new StringBuilder();
        append(value, appPackage);
        append(value, title);
        // Accessibility may report a different nested root class for the same visible
        // window on consecutive reads (for example ViewPager, RecyclerView, then an
        // obfuscated View). It is not an Activity identity and must not invalidate an
        // otherwise grounded operator command. Candidate signatures contain stable
        // candidate IDs, semantics, bounds and state, so screen changes remain guarded.
        for (String signature : candidateSignatures) {
            append(value, signature);
        }
        return sha256(value.toString());
    }

    static String normalizeVolatileText(String value) {
        String safe = value == null ? "" : value;
        String withoutClock = VOLATILE_CLOCK_PATTERN.matcher(safe)
                .replaceAll(" [time] ");
        return VOLATILE_KOREAN_DURATION_PATTERN.matcher(withoutClock)
                .replaceAll(" [duration] ")
                .trim()
                .replaceAll("\\s+", " ")
                .toLowerCase(Locale.ROOT);
    }

    private static void append(StringBuilder target, String value) {
        target.append(normalizeVolatileText(value)).append('\n');
    }

    private static String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte item : bytes) {
                hex.append(String.format(Locale.ROOT, "%02x", item));
            }
            return hex.toString();
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 unavailable", impossible);
        }
    }
}
