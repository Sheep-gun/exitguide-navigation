package com.exitguide.navigation.executor;

import android.graphics.Rect;
import android.util.DisplayMetrics;
import android.view.accessibility.AccessibilityNodeInfo;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

final class AccessibilityScreenReader {
    private static final int MAX_CANDIDATES = 250;
    private static final int MAX_DEPTH = 40;
    private static final int MAX_TEXT_LENGTH = 500;

    static final class CandidateBinding {
        final String candidateId;
        final List<Integer> path;
        final String fingerprint;
        final String riskLevel;
        final String semanticText;

        CandidateBinding(
                String candidateId,
                List<Integer> path,
                String fingerprint,
                String riskLevel,
                String semanticText
        ) {
            this.candidateId = candidateId;
            this.path = Collections.unmodifiableList(new ArrayList<>(path));
            this.fingerprint = fingerprint;
            this.riskLevel = riskLevel;
            this.semanticText = semanticText;
        }
    }

    static final class ScreenSnapshot {
        final JSONObject payload;
        final Map<String, CandidateBinding> bindings;
        final String appPackage;

        ScreenSnapshot(
                JSONObject payload,
                Map<String, CandidateBinding> bindings,
                String appPackage
        ) {
            this.payload = payload;
            this.bindings = Collections.unmodifiableMap(new LinkedHashMap<>(bindings));
            this.appPackage = appPackage;
        }
    }

    private final int screenHeight;

    AccessibilityScreenReader(DisplayMetrics metrics) {
        this.screenHeight = Math.max(1, metrics.heightPixels);
    }

    ScreenSnapshot read(AccessibilityNodeInfo root, String activityName) throws JSONException {
        JSONArray candidates = new JSONArray();
        Map<String, CandidateBinding> bindings = new LinkedHashMap<>();
        traverse(root, new ArrayList<>(), 0, candidates, bindings);

        JSONObject screen = new JSONObject();
        screen.put("window_title", truncate(windowTitle(root), MAX_TEXT_LENGTH));
        screen.put("activity_name", truncate(activityName, MAX_TEXT_LENGTH));
        screen.put("candidates", candidates);
        return new ScreenSnapshot(
                screen,
                bindings,
                truncate(string(root.getPackageName()), 240)
        );
    }

    AccessibilityNodeInfo resolve(
            AccessibilityNodeInfo root,
            CandidateBinding binding
    ) {
        AccessibilityNodeInfo current = root;
        for (Integer childIndex : binding.path) {
            if (current == null || childIndex < 0 || childIndex >= current.getChildCount()) {
                return null;
            }
            current = current.getChild(childIndex);
        }
        if (current == null || !binding.fingerprint.equals(nodeFingerprint(current, binding.path))) {
            return null;
        }
        return current;
    }

    private void traverse(
            AccessibilityNodeInfo node,
            List<Integer> path,
            int depth,
            JSONArray candidates,
            Map<String, CandidateBinding> bindings
    ) throws JSONException {
        if (node == null || depth > MAX_DEPTH || candidates.length() >= MAX_CANDIDATES) {
            return;
        }
        if (node.isVisibleToUser() && node.isEnabled() && node.isClickable()) {
            addCandidate(node, path, candidates, bindings);
        }
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo child = node.getChild(index);
            if (child == null) {
                continue;
            }
            path.add(index);
            traverse(child, path, depth + 1, candidates, bindings);
            path.remove(path.size() - 1);
            if (candidates.length() >= MAX_CANDIDATES) {
                return;
            }
        }
    }

    private void addCandidate(
            AccessibilityNodeInfo node,
            List<Integer> path,
            JSONArray candidates,
            Map<String, CandidateBinding> bindings
    ) throws JSONException {
        String label = preferredLabel(node);
        String parentSemantics = parentSemantics(node);
        String nearbyText = descendantText(node, 4);
        String iconSemantics = string(node.getContentDescription());
        String semanticText = String.join(
                " ",
                label,
                iconSemantics,
                parentSemantics,
                nearbyText
        );
        String riskLevel = NavigationSafetyPolicy.riskLevel(node, semanticText);
        String fingerprint = nodeFingerprint(node, path);
        String candidateId = "a11y_" + sha256(fingerprint).substring(0, 20);
        if (bindings.containsKey(candidateId)) {
            return;
        }

        JSONObject candidate = new JSONObject();
        candidate.put("candidate_id", candidateId);
        candidate.put("label", truncate(label, MAX_TEXT_LENGTH));
        candidate.put("role", role(node));
        candidate.put("risk_level", riskLevel);
        candidate.put("icon_semantics", truncate(iconSemantics, 200));
        candidate.put("nearby_text", truncate(nearbyText, MAX_TEXT_LENGTH));
        candidate.put("parent_semantics", truncate(parentSemantics, 300));
        candidate.put("position_bucket", positionBucket(node));
        candidate.put("clickable", node.isClickable());
        candidate.put("enabled", node.isEnabled());
        candidate.put("selected", node.isSelected());
        candidate.put("checked", node.isCheckable() ? node.isChecked() : JSONObject.NULL);
        candidates.put(candidate);
        bindings.put(
                candidateId,
                new CandidateBinding(candidateId, path, fingerprint, riskLevel, semanticText)
        );
    }

    static String nodeFingerprint(AccessibilityNodeInfo node, List<Integer> path) {
        StringBuilder builder = new StringBuilder();
        builder.append(string(node.getViewIdResourceName())).append('|');
        builder.append(string(node.getClassName())).append('|');
        builder.append(NavigationSafetyPolicy.normalize(preferredLabel(node))).append('|');
        for (Integer index : path) {
            builder.append(index).append('.');
        }
        return builder.toString();
    }

    private String positionBucket(AccessibilityNodeInfo node) {
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        int center = bounds.centerY();
        if (center < screenHeight / 3) {
            return "top";
        }
        if (center > screenHeight * 2 / 3) {
            return "bottom";
        }
        return "middle";
    }

    private static String preferredLabel(AccessibilityNodeInfo node) {
        for (CharSequence value : new CharSequence[] {
                node.getText(),
                node.getContentDescription(),
                node.getHintText()
        }) {
            String candidate = string(value).trim();
            if (!candidate.isEmpty()) {
                return candidate;
            }
        }
        return descendantText(node, 3);
    }

    private static String parentSemantics(AccessibilityNodeInfo node) {
        AccessibilityNodeInfo parent = node.getParent();
        return parent == null ? "" : descendantText(parent, 3);
    }

    private static String descendantText(AccessibilityNodeInfo node, int remaining) {
        if (node == null || remaining <= 0) {
            return "";
        }
        List<String> parts = new ArrayList<>();
        addUnique(parts, string(node.getText()));
        addUnique(parts, string(node.getContentDescription()));
        for (int index = 0; index < node.getChildCount() && parts.size() < remaining; index++) {
            AccessibilityNodeInfo child = node.getChild(index);
            if (child != null) {
                addUnique(parts, descendantText(child, remaining - parts.size()));
            }
        }
        return truncate(String.join(" ", parts), MAX_TEXT_LENGTH);
    }

    private static void addUnique(List<String> parts, String value) {
        String trimmed = value.trim();
        if (!trimmed.isEmpty() && !parts.contains(trimmed)) {
            parts.add(trimmed);
        }
    }

    private static String role(AccessibilityNodeInfo node) {
        String className = string(node.getClassName()).toLowerCase(Locale.ROOT);
        if (className.contains("switch")) return "switch";
        if (className.contains("checkbox")) return "checkbox";
        if (className.contains("radiobutton")) return "radio";
        if (className.contains("imagebutton")) return "icon_button";
        if (className.contains("button")) return "button";
        return "clickable";
    }

    private static String windowTitle(AccessibilityNodeInfo root) {
        if (root.getWindow() != null && root.getWindow().getTitle() != null) {
            return root.getWindow().getTitle().toString();
        }
        return preferredLabel(root);
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

    private static String truncate(String value, int maximum) {
        String safe = value == null ? "" : value;
        return safe.length() <= maximum ? safe : safe.substring(0, maximum);
    }

    private static String string(CharSequence value) {
        return value == null ? "" : value.toString();
    }
}
