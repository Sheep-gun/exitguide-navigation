# Product Spec

## 1. Product Goal

ExitGuide AI helps users complete an online task without being pulled away from their original intent. The MVP focuses on mobile screenshots where the user wants to cancel, unsubscribe, reject optional consent, or avoid extra payment.

The product does not declare a company illegal or malicious. It compares the user's chosen goal with visible UI elements and gives careful guidance such as "goal conflict possible", "check before tapping", and "recommended next action".

## 2. Primary User

- Users trying to cancel subscriptions or free trials
- Users who want to buy without optional add-ons
- Users rejecting ad or marketing consent
- Judges evaluating whether the team can connect AI reasoning to a usable product

## 3. MVP User Flow

1. Select a goal.
2. Upload a screenshot.
3. Wait for analysis.
4. Review risky elements, recommended action, and reasoning.
5. Save or view a Proof Card.

## 4. Goals

- Demonstrate an Android-first product experience.
- Analyze synthetic Korean UI screenshots safely.
- Return structured, controlled AI output.
- Combine LLM judgment with deterministic rule checks.
- Produce a clean demo flow for the rookie contest.

## 5. Non-Goals For The First MVP

- Automatic clicking on behalf of the user
- Live screen recording of every app
- Legal judgment about specific companies
- Crawling real corporate screens without permission
- Supporting every dark pattern category

## 6. Core Scenarios

### Subscription Cancellation

The screen contains a large "keep benefits" button and a smaller "continue cancellation" option. ExitGuide should identify which action conflicts with the cancellation goal.

### Free Trial Cancellation

The screen emphasizes remaining benefits and hides renewal timing. ExitGuide should surface auto-renewal or billing language.

### Add-On-Free Purchase

The checkout screen contains preselected insurance, membership, or donation options. ExitGuide should identify default checked add-ons and summarize the extra cost.

### Marketing Consent Rejection

The screen offers "agree all" prominently while separate optional consent items are lower or less visible. ExitGuide should distinguish required and optional consent.

### Account Deletion

The screen emphasizes keeping the account while the actual withdrawal action is less prominent. ExitGuide should separate data-loss warnings from the goal-aligned delete path.

## 7. Success Criteria

- The app can run on Android through Expo during development.
- The API accepts a goal and screenshot upload.
- The API returns structured JSON for UI elements, risks, recommendation, and proof card.
- The mobile UI displays a polished result screen.
- At least ten synthetic demo scenarios work end to end, including high-risk and low-risk comparison screens.
