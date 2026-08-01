# Providers

ExitGuide keeps OCR and LLM behind provider interfaces so the mobile app contract does not change when real services are added.

## Current Providers

- OCR: `mock`
- LLM: `mock`

The mock OCR provider infers a scenario from the uploaded filename or demo scenario. The mock LLM provider applies deterministic judgment rules for cancellation, add-on purchase, and consent rejection demos.
Provider names for `gemini_vision`, `gemini`, `openai_vision`, `openai`, `exaone_vision`, and `exaone` are wired for remote model calls. Provider names for `naver_clova_ocr`, `hyperclova`, and `upstage` are recognized by the backend and return clear setup errors until their HTTP clients are implemented. Missing setup notes name the exact environment variables that still need values.

`exaone_vision` and `exaone` are wired for OpenAI-compatible EXAONE endpoints. The default EXAONE base URL is FriendliAI Serverless Endpoints and the default model is `LGAI-EXAONE/K-EXAONE-236B-A23B`. Set `EXAONE_BASE_URL` to a Dedicated Endpoint or self-hosted EXAONE-compatible `/v1` base URL when that is where the model is deployed.

The `/v1/providers` endpoint returns the server-known provider options for the mobile app. The `/v1/status` endpoint returns `provider_ready`, `provider_notes`, and `supported_ai_providers`. The mobile app can send `provider_id`, `provider_api_key`, `provider_model`, and `provider_base_url` on analysis requests to use Google Gemini, OpenAI GPT, or EXAONE without editing `.env`.

## Environment Variables

```text
OCR_PROVIDER=mock
LLM_PROVIDER=mock
NAVER_CLOVA_OCR_URL=
NAVER_CLOVA_OCR_SECRET=
HYPERCLOVA_API_KEY=
HYPERCLOVA_MODEL=
GOOGLE_API_KEY=
GOOGLE_BASE_URL=https://generativelanguage.googleapis.com/v1beta
GEMINI_MODEL=gemini-3-flash-preview
UPSTAGE_API_KEY=
UPSTAGE_MODEL=solar-pro
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
EXAONE_API_KEY=
EXAONE_BASE_URL=https://api.friendli.ai/serverless/v1
EXAONE_MODEL=LGAI-EXAONE/K-EXAONE-236B-A23B
EXAONE_TEAM=
AI_PROVIDER_TIMEOUT_SECONDS=30
EXAONE_TIMEOUT_SECONDS=30
```

## Provider Contract

OCR provider:

```python
extract(image_bytes: bytes, filename: str | None, goal_id: str) -> ExtractedScreen
```

LLM provider:

```python
judge_elements(goal_id: str, screen: ExtractedScreen, goal_label: str | None = None) -> list[ElementJudgment]
```

The LLM should use the prompt builder in `app/services/prompting.py` and return controlled JSON. The rule engine remains responsible for assigning final risk levels and proof card text.
`goal_label` carries the user's free-form purpose when the mobile app sends one; providers should use it in the prompt while keeping `goal_id` on the nearest built-in goal for deterministic rule checks.

LLM JSON should be parsed through `app/services/model_output.py`. Unknown element IDs are ignored, missing element judgments fall back to `needs_check`, and invalid JSON is treated as a provider error rather than shown directly to the user.

For EXAONE:

- Set `OCR_PROVIDER=exaone_vision` to let the model extract visible UI elements from uploaded screenshots.
- Set `LLM_PROVIDER=exaone` to judge extracted elements through the EXAONE chat completions API.
- Set `EXAONE_MODEL` to the Friendli Dedicated Endpoint model or endpoint identifier, or to a model name accepted by the configured OpenAI-compatible EXAONE server.
- Keep `mock` providers for deterministic local quality gates when no EXAONE token is present.

For Google Gemini:

- Use app provider `google`, or set `OCR_PROVIDER=gemini_vision` and `LLM_PROVIDER=gemini`.
- Set `GOOGLE_API_KEY`, `GOOGLE_BASE_URL`, and `GEMINI_MODEL`.
- The default model is `gemini-3-flash-preview`, which accepts image and text input and returns text.
- Gemini 3 preview models use the `v1beta` Gemini REST surface. If the mobile app sends a Google base URL ending in `/v1` with a Gemini 3 or preview model, the backend normalizes it to `/v1beta` before calling `generateContent`.
- The backend uses Gemini REST `generateContent` with `inline_data`, `mime_type`, `system_instruction`, and JSON response mode fields.
- Gemini calls include response schemas, and the parser tolerates fenced JSON or short prose before the JSON object.
- If Gemini OCR still returns unstructured text, the API keeps analysis alive with a single screen-text element instead of returning 503. If Gemini LLM returns unstructured text, the rule fallback produces conservative `needs_check` style judgments.
- Screens with weak initial extraction but visible selectable rows can trigger a second Gemini OCR pass that asks for row-level UI extraction across checkboxes, toggles, radio controls, monetary add-ons, and primary CTA buttons. Selected optional rows are treated as goal conflicts when the user's goal is to avoid optional consent or add-ons.

For OpenAI GPT:

- Use app provider `gpt`, or set `OCR_PROVIDER=openai_vision` and `LLM_PROVIDER=openai`.
- Set `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL`.
- The backend calls the OpenAI Responses API for both screenshot structure extraction and element judgment.

## Safety Rules

- Do not log raw screenshot bytes.
- Do not make legal conclusions.
- Keep output JSON controlled and short.
- Let the rule engine re-check monetary impact, default selections, and prominent goal-conflicting buttons.
- Keep provider HTTP errors concise and never include API keys in logs or response details.
- Handled provider failures are logged to the API error log so phone-side 503s can be diagnosed after the fact.
