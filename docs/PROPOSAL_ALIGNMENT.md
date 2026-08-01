# Proposal Alignment

This note maps the rookie challenge proposal language to the current implementation so demo preparation stays focused.

## Implemented In MVP

- Goal-first flow: the mobile app starts from a selected user goal, then analyzes demos or screenshots.
- Controlled output: the API returns structured JSON for elements, risk, recommendation, alignment score, and Proof Card.
- Prompt transparency: `/v1/prompt/demo` previews the controlled JSON prompt for deterministic demo scenarios.
- Rule verification: the rule engine re-checks prominence, default selection, optional status, and monetary impact.
- Safe synthetic data: generated Korean UI screenshots avoid real company names and copyright risk.
- No legal conclusion: Proof Cards use guidance language and keep the disclaimer in every result.
- Low-risk comparison: clean checkout and required-terms scenarios verify that the system does not over-warn.
- Demo evidence: `scripts\New-DemoReport.ps1` writes `.artifacts\demo-report.md` from API outputs.
- Flow foundation: `/v1/analyze/flow` combines deterministic demo screens and the mobile app exposes a flow demo section.
- Screenshot sequence UX: the mobile app can pick multiple screenshots and call `/v1/analyze/flow/upload`.
- Flow explainability: flow results include `risk_path` so demos can show how risk changes screen by screen.
- Synthetic calibration: every generated fixture filename now maps through upload analysis with an expected high/medium/low risk label in the demo report.

## Next Strongest Additions

- Real OCR provider behind the existing `OcrProvider.extract` boundary.
- Real Korean LLM provider behind `LlmProvider.judge_elements`, using `prompting.py` and `model_output.py`.
- Continue labeling and tuning the current 15-screen synthetic fixture pack as the demo set grows.
- On-device capture or share-intent ingestion for smoother real-world screenshot sequences.
- APK/EAS build rehearsal once an Expo account and Android build choice are confirmed.
