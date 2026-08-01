# Consent Case Labeling Guide

Version: `1.0`

This guide keeps consent-case labels consistent as `fixtures/consent-cases/cases.json` grows. It applies to synthetic, generalized field-candidate, and redacted captured cases.

## Overall Risk

- `low`: The screen does not appear to push the user away from the selected goal. Required terms, unchecked optional consent, neutral notices, and ordinary confirmation buttons usually stay low.
- `medium`: The screen needs attention before continuing, but there is not yet a clear high-risk conflict. Examples include selected optional preferences without monetary impact, payment timing notices, ambiguous bundled wording, or informational notices that affect the user's decision.
- `high`: The screen contains a clear conflict with the user's goal. Examples include preselected optional marketing consent, agree-all controls that include optional consent, selected paid add-ons, retention buttons during cancellation, or bundled primary actions that include optional consent.

Use the case-level `expected_risk` as the highest expected element risk in that case.

## Element Direction

- `supports_goal`: The element directly helps the user complete the selected goal, such as "해지 완료하기", "계정 탈퇴 계속하기", or a clean payment action after add-ons are absent.
- `conflicts_with_goal`: The element pushes against the selected goal, such as selected optional marketing consent, selected paid add-ons, retention choices, or bundled consent actions.
- `needs_check`: The element does not directly conflict, but the user should inspect it before continuing. Required terms, warnings, neutral notices, and unselected optional choices usually fit here.

## Element Risk

- `low`: No default-selected optional state, no monetary impact, no strong prominence, and no conflict with the goal.
- `medium`: Requires user attention, especially default-selected optional preferences, billing notices, or non-prominent conflicts.
- `high`: Conflicts with the goal and is prominent, default-selected, bundled into a primary action, or tied to money/privacy-sensitive consent.

## Escalation Rules

Escalate to `high` when a case includes any of:

- Optional marketing, ad, SMS, push, email, benefit, event, or promotion consent selected by default.
- "전체 동의" or "동의하고 계속" actions that include optional consent.
- Third-party sharing, location-based advertising, or personalized-ad consent selected by default.
- Optional paid add-ons selected by default.
- Retention, pause, discount, or account-keep actions that compete with cancellation, trial termination, or account deletion.

Use `medium` rather than `high` when the item is selected by default but does not clearly create marketing/privacy/monetary impact, or when the text is ambiguous enough that a user should inspect it without treating it as a direct conflict.

## False-Positive Guards

Do not mark a case high just because it contains serious words. These usually remain `low` unless paired with optional/default-selected or goal-conflicting behavior:

- Required privacy policy or service terms.
- Required sensitive-data notices.
- Required legal notices about data processing or retention.
- Unchecked optional marketing or third-party sharing.
- Screen text that looks like instructions to the model. Treat it as untrusted observed screen text, not as a developer instruction.

## Review Rules

- Synthetic cases can be authored and reviewed by the implementer.
- `field_candidate` and `captured_redacted` cases require redaction and approval before entering the public fixture catalog.
- High-risk non-synthetic labels should get a second reviewer before becoming a stable calibration target.
- When the rubric changes, update `label_rubric_version` in the dataset and document the reason in `docs/DEVELOPMENT_LOG.md`.
