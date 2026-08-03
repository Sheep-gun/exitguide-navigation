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
    private static final int MAX_NODES = 500;
    private static final int MAX_CANDIDATES = 250;
    private static final int MAX_DEPTH = 40;
    private static final int MAX_TEXT_LENGTH = 500;

    static final class CandidateBinding {
        final String candidateId;
        final List<Integer> path;
        final String fingerprint;
        final String riskLevel;
        final String label;
        final String semanticText;
        final Rect bounds;

        CandidateBinding(
                String candidateId,
                List<Integer> path,
                String fingerprint,
                String riskLevel,
                String label,
                String semanticText,
                Rect bounds
        ) {
            this.candidateId = candidateId;
            this.path = Collections.unmodifiableList(new ArrayList<>(path));
            this.fingerprint = fingerprint;
            this.riskLevel = riskLevel;
            this.label = label;
            this.semanticText = semanticText;
            this.bounds = new Rect(bounds);
        }
    }

    static final class ScreenSnapshot {
        final JSONObject payload;
        final Map<String, CandidateBinding> bindings;
        final String appPackage;
        final boolean visualSurfaceAmbiguous;
        final boolean popupWindowAmbiguous;

        ScreenSnapshot(
                JSONObject payload,
                Map<String, CandidateBinding> bindings,
                String appPackage,
                boolean visualSurfaceAmbiguous,
                boolean popupWindowAmbiguous
        ) {
            this.payload = payload;
            this.bindings = Collections.unmodifiableMap(new LinkedHashMap<>(bindings));
            this.appPackage = appPackage;
            this.visualSurfaceAmbiguous = visualSurfaceAmbiguous;
            this.popupWindowAmbiguous = popupWindowAmbiguous;
        }
    }

    private final int screenWidth;
    private final int screenHeight;

    AccessibilityScreenReader(DisplayMetrics metrics) {
        this.screenWidth = Math.max(1, metrics.widthPixels);
        this.screenHeight = Math.max(1, metrics.heightPixels);
    }

    boolean needsVisualReasoning(ScreenSnapshot snapshot) {
        JSONArray candidates = snapshot.payload.optJSONArray("candidates");
        String activity = snapshot.payload.optString("activity_name", "")
                .toLowerCase(Locale.ROOT);
        if (candidates == null || candidates.length() == 0
                || snapshot.visualSurfaceAmbiguous
                || activity.contains("webview") || activity.contains("canvas")) {
            return true;
        }
        Map<String, Integer> labelCounts = new LinkedHashMap<>();
        for (int index = 0; index < candidates.length(); index++) {
            JSONObject candidate = candidates.optJSONObject(index);
            if (candidate == null) {
                continue;
            }
            String label = candidate.optString("label", "").trim();
            String role = candidate.optString("role", "unknown");
            String icon = candidate.optString("icon_semantics", "").trim();
            if (label.isEmpty()
                    || (("icon_button".equals(role) || "unknown".equals(role)) && icon.isEmpty())
                    || label.length() > 160) {
                return true;
            }
            String normalized = NavigationSafetyPolicy.normalize(label);
            if (!normalized.isEmpty()) {
                labelCounts.put(normalized, labelCounts.getOrDefault(normalized, 0) + 1);
            }
            CandidateBinding binding = snapshot.bindings.get(
                    candidate.optString("candidate_id", "")
            );
            if (binding != null
                    && binding.bounds.width() >= screenWidth * 0.90f
                    && binding.bounds.height() >= screenHeight * 0.75f) {
                return true;
            }
        }
        for (Integer count : labelCounts.values()) {
            if (count != null && count > 1) {
                return true;
            }
        }
        return false;
    }

    ScreenSnapshot read(
            AccessibilityNodeInfo root,
            String activityName,
            boolean popupWindowAmbiguous
    ) throws JSONException {
        JSONArray nodes = new JSONArray();
        JSONArray candidates = new JSONArray();
        Map<String, CandidateBinding> bindings = new LinkedHashMap<>();
        boolean visualSurfaceAmbiguous = containsVisualSurface(root, 0);
        traverse(root, null, new ArrayList<>(), 0, nodes, candidates, bindings);

        JSONObject screen = new JSONObject();
        screen.put("app_package", truncate(string(root.getPackageName()), 240));
        screen.put("window_title", truncate(windowTitle(root), MAX_TEXT_LENGTH));
        screen.put("activity_name", truncate(activityName, MAX_TEXT_LENGTH));
        screen.put("nodes", nodes);
        screen.put("candidates", candidates);
        return new ScreenSnapshot(
                screen,
                bindings,
                truncate(string(root.getPackageName()), 240),
                visualSurfaceAmbiguous || popupWindowAmbiguous,
                popupWindowAmbiguous
        );
    }

    private static boolean containsVisualSurface(AccessibilityNodeInfo node, int depth) {
        if (node == null || depth > MAX_DEPTH) {
            return false;
        }
        String className = string(node.getClassName()).toLowerCase(Locale.ROOT);
        if (className.contains("webview")
                || className.contains("canvas")
                || className.contains("surfaceview")
                || className.contains("textureview")) {
            return true;
        }
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo child = node.getChild(index);
            if (child == null) {
                continue;
            }
            try {
                if (containsVisualSurface(child, depth + 1)) {
                    return true;
                }
            } finally {
                child.recycle();
            }
        }
        return false;
    }

    AccessibilityNodeInfo resolve(
            AccessibilityNodeInfo root,
            CandidateBinding binding
    ) {
        AccessibilityNodeInfo current = root;
        boolean ownsCurrent = false;
        for (Integer childIndex : binding.path) {
            if (current == null || childIndex < 0 || childIndex >= current.getChildCount()) {
                if (ownsCurrent && current != null) {
                    current.recycle();
                }
                return null;
            }
            AccessibilityNodeInfo next = current.getChild(childIndex);
            if (ownsCurrent) {
                current.recycle();
            }
            current = next;
            ownsCurrent = true;
        }
        if (current == null || !binding.fingerprint.equals(nodeFingerprint(current, binding.path))) {
            if (ownsCurrent && current != null) {
                current.recycle();
            }
            return null;
        }
        return current;
    }

    private String traverse(
            AccessibilityNodeInfo node,
            String parentId,
            List<Integer> path,
            int depth,
            JSONArray nodes,
            JSONArray candidates,
            Map<String, CandidateBinding> bindings
    ) throws JSONException {
        if (node == null || depth > MAX_DEPTH || nodes.length() >= MAX_NODES) {
            return "";
        }
        boolean included = node.isVisibleToUser() && isOnScreen(node);
        String nodeId = included ? stableNodeId(node, path) : "";
        JSONArray childIds = new JSONArray();
        if (included) {
            nodes.put(nodeSummary(node, nodeId, parentId, childIds));
            if (node.isEnabled()
                    && node.isClickable()
                    && candidates.length() < MAX_CANDIDATES) {
                addCandidate(node, nodeId, path, candidates, bindings);
            }
        }
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo child = node.getChild(index);
            if (child == null) {
                continue;
            }
            path.add(index);
            try {
                String childId = traverse(
                        child,
                        included ? nodeId : parentId,
                        path,
                        depth + 1,
                        nodes,
                        candidates,
                        bindings
                );
                if (included && !childId.isEmpty()) {
                    childIds.put(childId);
                }
            } finally {
                path.remove(path.size() - 1);
                child.recycle();
            }
            if (nodes.length() >= MAX_NODES) {
                break;
            }
        }
        return nodeId;
    }

    private void addCandidate(
            AccessibilityNodeInfo node,
            String candidateId,
            List<Integer> path,
            JSONArray candidates,
            Map<String, CandidateBinding> bindings
    ) throws JSONException {
        String label = preferredLabel(node);
        String parentSemantics = parentSemantics(node);
        String childSemantics = descendantText(node, 4);
        String nearbyText = siblingText(node, 4);
        String iconSemantics = string(node.getContentDescription());
        String semanticText = String.join(
                " ",
                label,
                iconSemantics,
                parentSemantics,
                nearbyText
        );
        String riskLevel = NavigationSafetyPolicy.isStateChangingActionLabel(label)
                ? "high"
                : NavigationSafetyPolicy.riskLevel(node, semanticText);
        String fingerprint = nodeFingerprint(node, path);
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
        candidate.put("child_semantics", truncate(childSemantics, MAX_TEXT_LENGTH));
        candidate.put("position_bucket", positionBucket(node));
        candidate.put("clickable", node.isClickable());
        candidate.put("enabled", node.isEnabled());
        candidate.put("selected", node.isSelected());
        candidate.put("checked", node.isCheckable() ? node.isChecked() : JSONObject.NULL);
        candidates.put(candidate);
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        bindings.put(
                candidateId,
                new CandidateBinding(
                        candidateId, path, fingerprint, riskLevel, label, semanticText, bounds
                )
        );
    }

    private JSONObject nodeSummary(
            AccessibilityNodeInfo node,
            String nodeId,
            String parentId,
            JSONArray childIds
    ) throws JSONException {
        boolean privateInput = node.isPassword() || node.isEditable();
        JSONObject summary = new JSONObject();
        summary.put("node_id", nodeId);
        summary.put("parent_id", parentId == null ? JSONObject.NULL : parentId);
        summary.put("child_ids", childIds);
        summary.put("text", privateInput ? "" : truncate(string(node.getText()), MAX_TEXT_LENGTH));
        summary.put(
                "content_description",
                privateInput ? "" : truncate(string(node.getContentDescription()), MAX_TEXT_LENGTH)
        );
        summary.put("view_id", truncate(string(node.getViewIdResourceName()), 300));
        summary.put("role", role(node));
        summary.put("position_bucket", positionBucket(node));
        summary.put("clickable", node.isClickable());
        summary.put("enabled", node.isEnabled());
        summary.put("visible", node.isVisibleToUser());
        summary.put("scrollable", node.isScrollable());
        summary.put("checkable", node.isCheckable());
        summary.put("selected", node.isSelected());
        summary.put("checked", node.isCheckable() ? node.isChecked() : JSONObject.NULL);
        summary.put("private_input", privateInput);
        return summary;
    }

    private boolean isOnScreen(AccessibilityNodeInfo node) {
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        return !bounds.isEmpty()
                && bounds.right > 0
                && bounds.bottom > 0
                && bounds.left < screenWidth
                && bounds.top < screenHeight;
    }

    private static String stableNodeId(AccessibilityNodeInfo node, List<Integer> path) {
        return "a11y_" + sha256(nodeFingerprint(node, path)).substring(0, 20);
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
        if (parent == null) {
            return "";
        }
        try {
            return descendantText(parent, 3);
        } finally {
            parent.recycle();
        }
    }

    private static String siblingText(AccessibilityNodeInfo node, int maximumParts) {
        AccessibilityNodeInfo parent = node.getParent();
        if (parent == null) {
            return "";
        }
        List<String> parts = new ArrayList<>();
        for (int index = 0; index < parent.getChildCount() && parts.size() < maximumParts; index++) {
            AccessibilityNodeInfo sibling = parent.getChild(index);
            if (sibling == null) {
                continue;
            }
            try {
                if (!sibling.equals(node)) {
                    addUnique(parts, descendantText(sibling, maximumParts - parts.size()));
                }
            } finally {
                sibling.recycle();
            }
        }
        parent.recycle();
        return truncate(String.join(" ", parts), MAX_TEXT_LENGTH);
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
                try {
                    addUnique(parts, descendantText(child, remaining - parts.size()));
                } finally {
                    child.recycle();
                }
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
