package com.exitguide.navigation.executor;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.util.Base64;

import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Safe reuse of the original ExitGuide screenshot/OCR pipeline.
 *
 * <p>OCR may enrich only an accessibility-grounded candidate. It never
 * creates a candidate or a coordinate click target. The image sent to the
 * VLM is privacy-masked and annotated with the existing candidate IDs.</p>
 */
final class VisualScreenAugmenter implements AutoCloseable {
    interface Callback {
        void onReady(String screenshotDataUrl, int mergedOcrLines);
    }

    private static final int MAX_SCREENSHOT_EDGE = 900;
    private static final int MAX_TEXT_LENGTH = 500;
    private static final Pattern EMAIL = Pattern.compile(
            "\\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}\\b",
            Pattern.CASE_INSENSITIVE
    );
    private static final Pattern USER_HANDLE = Pattern.compile(
            "(?<![\\w@])@[0-9A-Za-z._-]{2,64}\\b"
    );
    private static final Pattern ACCOUNT_CONTEXT = Pattern.compile(
            "프로필|계정|아이디|\\b(?:profile|account|username|user\\s*id)\\b",
            Pattern.CASE_INSENSITIVE
    );
    private static final Pattern ACCOUNT_IDENTIFIER_TOKEN =
            Pattern.compile("[0-9A-Za-z._-]{3,64}");
    private static final Pattern MASKED_KOREAN_NAME = Pattern.compile(
            "(?<![가-힣])(?:[가-힣]{1,2}\\*+[가-힣]{1,2})(?![가-힣])"
    );
    private static final Pattern PHONE = Pattern.compile(
            "(?<!\\d)(?:(?:\\+?82[- ]?)?0?1[016789][- ]?\\d{3,4}[- ]?\\d{4}"
                    + "|0(?:2|[3-6]\\d)[- ]?\\d{3,4}[- ]?\\d{4}"
                    + "|1[568]\\d{2}[- ]?\\d{4})(?!\\d)"
    );
    private static final Pattern CURRENCY = Pattern.compile(
            "(?<![\\w])(?:(?:₩|\\$|€)\\s?\\d[\\d,]*(?:\\.\\d{1,2})?"
                    + "|\\d[\\d,]*(?:\\.\\d{1,2})?\\s?(?:원|KRW|USD|달러))(?![\\w])",
            Pattern.CASE_INSENSITIVE
    );
    private static final Pattern LONG_NUMBER = Pattern.compile("(?<!\\d)\\d{7,}(?!\\d)");
    private static final Pattern HONORIFIC_NAME = Pattern.compile(".*[가-힣]{2,4}\\s*님.*");
    private static final Pattern STREET_ADDRESS = Pattern.compile(
            ".*(?:주소|[가-힣0-9]+(?:로|길)\\s*\\d+).*"
    );

    private final TextRecognizer recognizer = TextRecognition.getClient(
            new KoreanTextRecognizerOptions.Builder().build()
    );

    void augment(
            Bitmap screenshot,
            AccessibilityScreenReader.ScreenSnapshot snapshot,
            Callback callback
    ) {
        Set<String> accountIdentifiers = contextualAccountIdentifiers(snapshot);
        recognizer.process(InputImage.fromBitmap(screenshot, 0))
                .addOnSuccessListener(result -> callback.onReady(
                        buildMaskedOverlayDataUrl(
                                screenshot, snapshot, result, accountIdentifiers
                        ),
                        mergeOcrIntoExistingCandidates(snapshot, result, accountIdentifiers)
                ))
                .addOnFailureListener(error -> callback.onReady(
                        buildMaskedOverlayDataUrl(
                                screenshot, snapshot, null, accountIdentifiers
                        ),
                        0
                ));
    }

    @Override
    public void close() {
        recognizer.close();
    }

    static boolean isSensitiveText(String value) {
        String normalized = value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            return false;
        }
        return hasDirectSensitiveData(normalized)
                || !contextualAccountIdentifiers(normalized).isEmpty();
    }

    private static boolean hasDirectSensitiveData(String normalized) {
        return EMAIL.matcher(normalized).find()
                || USER_HANDLE.matcher(normalized).find()
                || MASKED_KOREAN_NAME.matcher(normalized).find()
                || PHONE.matcher(normalized).find()
                || CURRENCY.matcher(normalized).find()
                || LONG_NUMBER.matcher(normalized).find()
                || HONORIFIC_NAME.matcher(normalized).matches()
                || STREET_ADDRESS.matcher(normalized).matches()
                || normalized.contains("bearer ")
                || normalized.contains("access token")
                || normalized.contains("session token")
                || normalized.contains("password")
                || normalized.contains("비밀번호")
                || normalized.contains("인증번호");
    }

    static String redactSensitiveText(String value) {
        String source = value == null ? "" : value;
        return redactSensitiveText(source, contextualAccountIdentifiers(source));
    }

    private static String redactSensitiveText(
            String value,
            Set<String> accountIdentifiers
    ) {
        String source = value == null ? "" : value;
        if (hasDirectSensitiveData(source.toLowerCase(Locale.ROOT))) {
            return "[redacted]";
        }
        Matcher matcher = ACCOUNT_IDENTIFIER_TOKEN.matcher(source);
        StringBuffer output = new StringBuffer();
        while (matcher.find()) {
            String token = matcher.group();
            String replacement = accountIdentifiers.contains(token.toLowerCase(Locale.ROOT))
                    ? "[account]" : token;
            matcher.appendReplacement(output, Matcher.quoteReplacement(replacement));
        }
        matcher.appendTail(output);
        return output.toString();
    }

    private static Set<String> contextualAccountIdentifiers(String value) {
        Set<String> identifiers = new LinkedHashSet<>();
        String source = value == null ? "" : value;
        if (!ACCOUNT_CONTEXT.matcher(source).find()) {
            return identifiers;
        }
        Matcher matcher = ACCOUNT_IDENTIFIER_TOKEN.matcher(source);
        while (matcher.find()) {
            String token = matcher.group();
            boolean hasLetter = false;
            boolean hasDigitOrSeparator = false;
            for (int index = 0; index < token.length(); index++) {
                char character = token.charAt(index);
                hasLetter |= Character.isLetter(character);
                hasDigitOrSeparator |= Character.isDigit(character)
                        || character == '.' || character == '_' || character == '-';
            }
            if (hasLetter && hasDigitOrSeparator) {
                identifiers.add(token.toLowerCase(Locale.ROOT));
            }
        }
        return identifiers;
    }

    private static Set<String> contextualAccountIdentifiers(
            AccessibilityScreenReader.ScreenSnapshot snapshot
    ) {
        Set<String> identifiers = new LinkedHashSet<>();
        identifiers.addAll(contextualAccountIdentifiers(
                snapshot.payload.optString("window_title", "")
        ));
        JSONArray nodes = snapshot.payload.optJSONArray("nodes");
        if (nodes != null) {
            for (int index = 0; index < nodes.length(); index++) {
                JSONObject node = nodes.optJSONObject(index);
                if (node != null) {
                    identifiers.addAll(contextualAccountIdentifiers(
                            node.optString("text", "")
                    ));
                    identifiers.addAll(contextualAccountIdentifiers(
                            node.optString("content_description", "")
                    ));
                }
            }
        }
        JSONArray candidates = snapshot.payload.optJSONArray("candidates");
        if (candidates != null) {
            String[] fields = {
                    "label", "icon_semantics", "nearby_text", "parent_semantics",
                    "child_semantics", "visual_role", "visual_region"
            };
            for (int index = 0; index < candidates.length(); index++) {
                JSONObject candidate = candidates.optJSONObject(index);
                if (candidate == null) {
                    continue;
                }
                for (String field : fields) {
                    identifiers.addAll(contextualAccountIdentifiers(
                            candidate.optString(field, "")
                    ));
                }
            }
        }
        return identifiers;
    }

    private static boolean containsAccountIdentifier(
            String value,
            Set<String> accountIdentifiers
    ) {
        Matcher matcher = ACCOUNT_IDENTIFIER_TOKEN.matcher(value == null ? "" : value);
        while (matcher.find()) {
            if (accountIdentifiers.contains(matcher.group().toLowerCase(Locale.ROOT))) {
                return true;
            }
        }
        return false;
    }

    static void redactSnapshotInPlace(AccessibilityScreenReader.ScreenSnapshot snapshot) {
        Set<String> accountIdentifiers = contextualAccountIdentifiers(snapshot);
        JSONArray nodes = snapshot.payload.optJSONArray("nodes");
        if (nodes != null) {
            for (int index = 0; index < nodes.length(); index++) {
                JSONObject node = nodes.optJSONObject(index);
                if (node == null) {
                    continue;
                }
                for (String field : new String[] {"text", "content_description"}) {
                    String value = node.optString(field, "");
                    String redacted = redactSensitiveText(value, accountIdentifiers);
                    if (!redacted.equals(value)) {
                        put(node, field, redacted);
                    }
                }
            }
        }
        JSONArray candidates = snapshot.payload.optJSONArray("candidates");
        if (candidates == null) {
            return;
        }
        String[] semanticFields = {
                "label", "icon_semantics", "nearby_text", "parent_semantics", "child_semantics"
        };
        for (int index = 0; index < candidates.length(); index++) {
            JSONObject candidate = candidates.optJSONObject(index);
            if (candidate == null) {
                continue;
            }
            for (String field : semanticFields) {
                String value = candidate.optString(field, "");
                String redacted = redactSensitiveText(value, accountIdentifiers);
                if (!redacted.equals(value)) {
                    put(candidate, field, redacted);
                }
            }
        }
        String title = snapshot.payload.optString("window_title", "");
        String redactedTitle = redactSensitiveText(title, accountIdentifiers);
        if (!redactedTitle.equals(title)) {
            put(snapshot.payload, "window_title", redactedTitle);
        }
    }

    private static int mergeOcrIntoExistingCandidates(
            AccessibilityScreenReader.ScreenSnapshot snapshot,
            Text result,
            Set<String> accountIdentifiers
    ) {
        JSONArray candidates = snapshot.payload.optJSONArray("candidates");
        if (candidates == null || result == null) {
            return 0;
        }
        Map<String, JSONObject> candidateById = new LinkedHashMap<>();
        for (int index = 0; index < candidates.length(); index++) {
            JSONObject candidate = candidates.optJSONObject(index);
            if (candidate != null) {
                candidateById.put(candidate.optString("candidate_id", ""), candidate);
            }
        }
        int merged = 0;
        for (Text.TextBlock block : result.getTextBlocks()) {
            for (Text.Line line : block.getLines()) {
                String label = clean(line.getText());
                Rect bounds = line.getBoundingBox();
                if (label.isEmpty()
                        || isSensitiveText(label)
                        || containsAccountIdentifier(label, accountIdentifiers)
                        || bounds == null
                        || bounds.isEmpty()) {
                    continue;
                }
                AccessibilityScreenReader.CandidateBinding binding = nearestBinding(
                        snapshot.bindings, bounds
                );
                JSONObject candidate = binding == null
                        ? null : candidateById.get(binding.candidateId);
                if (candidate == null) {
                    continue;
                }
                String currentLabel = clean(candidate.optString("label", ""));
                if (currentLabel.isEmpty()) {
                    put(candidate, "label", truncate(label, MAX_TEXT_LENGTH));
                    merged++;
                    continue;
                }
                String nearby = clean(candidate.optString("nearby_text", ""));
                String normalizedNearby = NavigationSafetyPolicy.normalize(nearby);
                String normalizedLabel = NavigationSafetyPolicy.normalize(label);
                if (!normalizedLabel.isEmpty() && !normalizedNearby.contains(normalizedLabel)) {
                    put(
                            candidate,
                            "nearby_text",
                            truncate((nearby + " " + label).trim(), MAX_TEXT_LENGTH)
                    );
                    merged++;
                }
            }
        }
        return merged;
    }

    private static AccessibilityScreenReader.CandidateBinding nearestBinding(
            Map<String, AccessibilityScreenReader.CandidateBinding> bindings,
            Rect ocrBounds
    ) {
        AccessibilityScreenReader.CandidateBinding best = null;
        double bestScore = Double.NEGATIVE_INFINITY;
        int centerX = ocrBounds.centerX();
        int centerY = ocrBounds.centerY();
        for (AccessibilityScreenReader.CandidateBinding binding : bindings.values()) {
            Rect bounds = binding.bounds;
            if (bounds == null || bounds.isEmpty()) {
                continue;
            }
            double score;
            if (bounds.contains(centerX, centerY)) {
                score = 1_000_000.0 - (double) bounds.width() * bounds.height();
            } else {
                int verticalOverlap = Math.min(bounds.bottom, ocrBounds.bottom)
                        - Math.max(bounds.top, ocrBounds.top);
                double overlapRatio = verticalOverlap <= 0 ? 0.0
                        : (double) verticalOverlap
                        / Math.max(1, Math.min(bounds.height(), ocrBounds.height()));
                int horizontalGap = Math.max(
                        0,
                        Math.max(bounds.left - ocrBounds.right, ocrBounds.left - bounds.right)
                );
                int permittedGap = Math.max(24, Math.round(bounds.width() * 0.25f));
                if (overlapRatio < 0.35 || horizontalGap > permittedGap) {
                    continue;
                }
                score = 5_000.0 + overlapRatio * 1_000.0
                        - horizontalGap - Math.abs(bounds.centerY() - centerY) * 2.0;
            }
            if (score > bestScore) {
                bestScore = score;
                best = binding;
            }
        }
        return best;
    }

    private static String buildMaskedOverlayDataUrl(
            Bitmap source,
            AccessibilityScreenReader.ScreenSnapshot snapshot,
            Text ocr,
            Set<String> accountIdentifiers
    ) {
        Bitmap annotated = source.copy(Bitmap.Config.ARGB_8888, true);
        if (annotated == null) {
            return "";
        }
        Canvas canvas = new Canvas(annotated);
        Paint mask = new Paint(Paint.ANTI_ALIAS_FLAG);
        mask.setColor(Color.rgb(32, 33, 36));
        mask.setStyle(Paint.Style.FILL);

        for (AccessibilityScreenReader.CandidateBinding binding : snapshot.bindings.values()) {
            if (isSensitiveText(binding.semanticText)
                    || containsAccountIdentifier(binding.semanticText, accountIdentifiers)) {
                canvas.drawRect(binding.bounds, mask);
            }
        }
        if (ocr != null) {
            for (Text.TextBlock block : ocr.getTextBlocks()) {
                for (Text.Line line : block.getLines()) {
                    Rect bounds = line.getBoundingBox();
                    if (bounds != null && !bounds.isEmpty()
                            && (isSensitiveText(line.getText())
                            || containsAccountIdentifier(line.getText(), accountIdentifiers))) {
                        canvas.drawRect(bounds, mask);
                    }
                }
            }
        }

        Paint border = new Paint(Paint.ANTI_ALIAS_FLAG);
        border.setColor(Color.rgb(0, 220, 160));
        border.setStyle(Paint.Style.STROKE);
        border.setStrokeWidth(Math.max(2f, annotated.getWidth() / 480f));
        Paint textBackground = new Paint(Paint.ANTI_ALIAS_FLAG);
        textBackground.setColor(Color.argb(220, 0, 0, 0));
        textBackground.setStyle(Paint.Style.FILL);
        Paint textPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        textPaint.setColor(Color.WHITE);
        textPaint.setTextSize(Math.max(22f, annotated.getWidth() / 52f));

        for (AccessibilityScreenReader.CandidateBinding binding : snapshot.bindings.values()) {
            Rect bounds = binding.bounds;
            if (bounds == null || bounds.isEmpty()) {
                continue;
            }
            canvas.drawRect(bounds, border);
            String tag = binding.candidateId;
            float tagWidth = textPaint.measureText(tag);
            float left = Math.max(0f, Math.min(bounds.left, annotated.getWidth() - tagWidth - 8f));
            float baseline = Math.max(textPaint.getTextSize(), bounds.top + textPaint.getTextSize());
            canvas.drawRect(
                    left,
                    baseline - textPaint.getTextSize(),
                    Math.min(annotated.getWidth(), left + tagWidth + 8f),
                    baseline + 4f,
                    textBackground
            );
            canvas.drawText(tag, left + 4f, baseline, textPaint);
        }

        Bitmap scaled = resize(annotated, MAX_SCREENSHOT_EDGE);
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        scaled.compress(Bitmap.CompressFormat.JPEG, 62, output);
        if (scaled != annotated) {
            scaled.recycle();
        }
        annotated.recycle();
        return "data:image/jpeg;base64,"
                + Base64.encodeToString(output.toByteArray(), Base64.NO_WRAP);
    }

    private static Bitmap resize(Bitmap source, int maxEdge) {
        int largest = Math.max(source.getWidth(), source.getHeight());
        if (largest <= maxEdge) {
            return source;
        }
        float scale = (float) maxEdge / largest;
        return Bitmap.createScaledBitmap(
                source,
                Math.max(1, Math.round(source.getWidth() * scale)),
                Math.max(1, Math.round(source.getHeight() * scale)),
                true
        );
    }

    private static void put(JSONObject object, String key, String value) {
        try {
            object.put(key, value);
        } catch (Exception ignored) {
            // The target object and strings are bounded and valid in normal operation.
        }
    }

    private static String clean(String value) {
        return value == null ? "" : value.trim().replaceAll("\\s+", " ");
    }

    private static String truncate(String value, int maximum) {
        return value.length() <= maximum ? value : value.substring(0, maximum);
    }
}
