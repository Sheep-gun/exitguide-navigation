# Demo Script

## 1. Opening

ExitGuide AI helps users keep their original goal while navigating confusing cancellation, checkout, or consent screens.

Before a recorded demo, run:

```powershell
.\scripts\Start-JudgeDemo.ps1
.\scripts\New-DemoReport.ps1
```

This starts the desktop API/web demo and writes `.artifacts/demo-report.md` so the spoken demo and API outputs stay aligned.
Open `http://127.0.0.1:8020`, load the catalog, and point out the readiness chips before starting scenario analysis.

## 2. Scenario: Subscription Cancellation

1. Open the app.
2. Select "Cancel subscription".
3. Upload the synthetic cancellation screenshot.
4. Show that the large retention button conflicts with the goal.
5. Show the recommended action and reasoning.
6. Open the Proof Card.

## 3. Scenario: Free Trial Renewal

1. Select "Free trial renewal" from the phone demo list.
2. Show the auto-renewal timing and monthly charge evidence.
3. Show that "Cancel trial now" is the goal-aligned action.
4. Open the Proof Card.

## 4. Scenario: Add-On-Free Purchase

1. Select "Buy without extra charges".
2. Upload the checkout screenshot.
3. Show preselected add-ons and extra cost signals.
4. Show the recommended unchecked path.
5. Run "Clean checkout" to show the system does not over-warn when optional add-ons are already unchecked.

## 5. Scenario: Marketing Consent Rejection

1. Select "Reject optional marketing consent".
2. Upload the consent screenshot.
3. Show which consent items are optional.
4. Show the safe next action.
5. Run "Required terms only" to show the low-risk comparison path.

## 6. Scenario: Account Deletion

1. Select "Account deletion" from the phone demo list.
2. Show that the large keep-account button conflicts with the deletion goal.
3. Show that data-loss language is classified as a check item, not a legal conclusion.
4. Share the Proof Card if a judge asks for the structured evidence.

## 7. Scenario: Multi-Screen Flow

1. Open the Flow demo section.
2. Run "Cancellation path" or "Add-on risk contrast".
3. Show the flow-level alignment score, risk path, and Proof Card.
4. If testing on a phone, choose 2-6 screenshots in Screenshot flow and run the same flow-level analysis on uploaded images.

## 8. Scenario: Synthetic Calibration

1. In the web demo, load the catalog.
2. Use the Synthetic uploads section to run a fixture through the real upload endpoint.
3. Compare expected risk with the rendered output and the calibration table in `.artifacts/demo-report.md`.

## 9. Closing

The service does not judge companies. It compares the user's goal with the current screen and gives controlled, explainable guidance.
