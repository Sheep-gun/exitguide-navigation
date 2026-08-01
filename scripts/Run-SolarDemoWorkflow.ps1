param(
  [string]$OutputRoot = "",
  [string]$SourceCsvPath = "",
  [string]$Model = "solar-pro3",
  [int]$MaxCases = 6,
  [int]$HttpTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

$CommonModule = Join-Path $PSScriptRoot "ExitGuide.Common.psm1"
Import-Module $CommonModule -Force

$RepoRoot = Get-ExitGuideRepoRoot

if (-not $OutputRoot) {
  $OutputRoot = Join-Path $RepoRoot ".artifacts/solar-demo-workflow"
}

if (-not [System.IO.Path]::IsPathRooted($OutputRoot)) {
  $OutputRoot = Join-Path $RepoRoot $OutputRoot
}

Test-ExitGuideChildPath -Path $OutputRoot -Parent $RepoRoot | Out-Null

if (-not $SourceCsvPath) {
  $SourceDir = Join-Path $RepoRoot ".artifacts/public-datasets/raw/data_go_kr_kca_standard_answers"
  $SourceCsv = Get-ChildItem -LiteralPath $SourceDir -Filter "*.csv" -File -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if (-not $SourceCsv) {
    throw "KCA standard answer CSV was not found. Run .\scripts\Collect-PublicDatasets.ps1 first."
  }
  $SourceCsvPath = $SourceCsv.FullName
}

if (-not [System.IO.Path]::IsPathRooted($SourceCsvPath)) {
  $SourceCsvPath = Join-Path $RepoRoot $SourceCsvPath
}

Test-ExitGuideChildPath -Path $SourceCsvPath -Parent $RepoRoot | Out-Null

$ApiKey = $env:UPSTAGE_API_KEY
$EnvPath = Join-Path $RepoRoot ".env"
if (-not $ApiKey -and (Test-Path -LiteralPath $EnvPath)) {
  foreach ($Line in Get-Content -LiteralPath $EnvPath) {
    if ($Line -match "^UPSTAGE_API_KEY=(.+)$") {
      $ApiKey = $Matches[1].Trim().Trim('"')
      break
    }
  }
}

$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if (-not $PythonCommand) {
    throw "Python was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
  }
  $Python = $PythonCommand.Source
}

$Script = @'
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


SOURCE_CSV = Path(sys.argv[1]).resolve()
OUTPUT_ROOT = Path(sys.argv[2]).resolve()
MODEL = sys.argv[3]
MAX_CASES = int(sys.argv[4])
HTTP_TIMEOUT_SECONDS = int(sys.argv[5])
API_KEY = os.environ.get("UPSTAGE_API_KEY_FOR_WORKFLOW", "")
API_BASE = os.environ.get("UPSTAGE_API_BASE", "https://api.upstage.ai/v1").rstrip("/")

DEFAULT_CASE_NUMBERS = ["873", "863", "846", "435", "970", "865"]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def read_kca_csv(path: Path) -> list[dict[str, str]]:
    last_error: Exception | None = None
    for encoding in ("cp949", "utf-8-sig", "utf-8"):
        try:
            rows = []
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.reader(handle)
                _header = next(reader)
                for raw in reader:
                    if len(raw) < 5:
                        continue
                    rows.append({
                        "number": raw[0].strip(),
                        "product": raw[1].strip(),
                        "category": raw[2].strip(),
                        "question": raw[3].strip(),
                        "answer": raw[4].strip(),
                    })
            return rows
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Could not read {path}: {last_error}")


def first_non_empty(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = (row.get(key) or "").strip()
        if value:
            return value
    return ""


def compact(value: str, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def infer_demo_flow(row: dict[str, str]) -> dict:
    case_no = first_non_empty(row, "number")
    product = first_non_empty(row, "product")
    category = first_non_empty(row, "category")
    question = first_non_empty(row, "question")

    templates = {
        "873": {
            "user_goal": "Cancel an OTT subscription now and avoid an unfair no-refund stop screen.",
            "screen_context": "Subscription cancellation screen says the current billing cycle cannot be refunded.",
            "visible_screen_text": [
                "Membership cancellation",
                "No refund is available within the current billing cycle.",
                "Cancellation applies from the next billing date.",
                "Keep membership",
                "Continue cancellation"
            ],
        },
        "863": {
            "user_goal": "Cancel an annual online video subscription and avoid an excessive penalty.",
            "screen_context": "Cancellation screen says 50 percent of the remaining commitment will be charged.",
            "visible_screen_text": [
                "Annual plan cancellation",
                "50 percent of the remaining commitment will be charged as a penalty.",
                "Benefits end immediately after cancellation.",
                "Keep plan",
                "Accept penalty and cancel"
            ],
        },
        "846": {
            "user_goal": "Cancel an online lecture contract and request a refund for the unused period.",
            "screen_context": "Online lecture service says cancellation is allowed only after three or fewer lessons.",
            "visible_screen_text": [
                "Course cancellation request",
                "Mid-term cancellation is allowed only when three or fewer lessons were taken.",
                "You have taken four lessons and are not eligible for a refund.",
                "Contact support",
                "Cancel request"
            ],
        },
        "435": {
            "user_goal": "Cancel a one-year mobile app subscription and request a refund for the unused period.",
            "screen_context": "Mobile app subscription screen says only cancellations within 48 hours receive a full refund.",
            "visible_screen_text": [
                "Premium plan cancellation",
                "Full refund is available only within 48 hours after payment.",
                "No refund is provided for the remaining period.",
                "Keep benefits",
                "Request cancellation"
            ],
        },
        "970": {
            "user_goal": "Cancel a water purifier rental contract made through door-to-door sales shortly after installation.",
            "screen_context": "Rental contract screen says cancellation is unavailable after installation.",
            "visible_screen_text": [
                "Rental contract cancellation",
                "Installed products cannot be cancelled.",
                "Keeping the contract preserves promotional benefits.",
                "Keep contract",
                "Ask about cancellation"
            ],
        },
        "865": {
            "user_goal": "Withdraw from a stock auto-trading information service sold by phone solicitation and request a refund.",
            "screen_context": "Information service screen says refund is unavailable because the product includes intellectual property.",
            "visible_screen_text": [
                "Service withdrawal",
                "This digital content includes intellectual property and is non-refundable.",
                "Provided information cannot be recovered.",
                "Continue service",
                "Request withdrawal"
            ],
        },
    }

    fallback = {
        "user_goal": f"Cancel or refund a consumer contract related to {product}.",
        "screen_context": f"Service screen related to {category} indicates cancellation or refund restrictions.",
        "visible_screen_text": [
            "Contract cancellation",
            compact(question, 160),
            "Refund may be restricted under the terms.",
            "Keep contract",
            "Request cancellation"
        ],
    }
    flow = templates.get(case_no, fallback)
    return {
        "case_number": case_no,
        "product": product,
        "category": category,
        "question": question,
        "answer": first_non_empty(row, "answer"),
        **flow,
    }


def select_cases(rows: list[dict[str, str]], max_cases: int) -> list[dict]:
    by_number = {first_non_empty(row, "number"): row for row in rows}
    selected = []
    for number in DEFAULT_CASE_NUMBERS:
        row = by_number.get(number)
        if row:
            selected.append(infer_demo_flow(row))
    if len(selected) >= max_cases:
        return selected[:max_cases]

    seen = {item["case_number"] for item in selected}
    scored = []
    for row in rows:
        number = first_non_empty(row, "number")
        if number in seen:
            continue
        text_length = len(" ".join(row.values()))
        scored.append((text_length, number, row))
    for _score, _number, row in sorted(scored, key=lambda item: (-item[0], item[1])):
        selected.append(infer_demo_flow(row))
        if len(selected) >= max_cases:
            break
    return selected


SYSTEM_PROMPT = """\
You are ExitGuide Workflow Agent.

Your job is not legal advice. Your job is to imitate the planned ExitGuide backend workflow for a mobile app demo.

Input:
- user_goal: what the user wants to do
- visible_screen_text: text that appears on a consumer-facing screen
- consumer_reference_case: a Korean Consumer Agency standard Q/A case

Reasoning policy:
- Identify whether the screen text conflicts with the user's goal.
- Use the consumer reference case only as practical guidance, not as a binding legal conclusion.
- Prefer conservative wording such as "may request", "needs confirmation", and "do not stop only because the screen says refund unavailable".
- Extract short evidence quotes from the screen and the reference case.
- Never claim a guaranteed legal outcome.

Return only valid JSON with this schema:
{
  "case_number": "string",
  "risk_level": "low|medium|high|needs_check",
  "user_goal": "string",
  "screen_summary": "string",
  "goal_conflicts": [
    {
      "screen_text": "string",
      "risk_signal": "cancel_friction|refund_limit|excessive_penalty|cooling_off_block|misleading_retention|needs_check",
      "why_it_matters": "string"
    }
  ],
  "reference_guidance": {
    "matched_point": "string",
    "safe_user_facing_summary": "string",
    "not_legal_advice": true
  },
  "recommended_action": {
    "primary": "string",
    "avoid": "string",
    "next_evidence_to_collect": ["string"]
  },
  "demo_workflow_steps": [
    {
      "step": 1,
      "actor": "user|mobile_app|api|retrieval|agent",
      "output": "string"
    }
  ],
  "evidence_quotes": [
    {
      "source": "screen|consumer_reference_case",
      "quote": "string"
    }
  ],
  "confidence": "low|medium|high"
}
"""


def build_user_payload(case: dict) -> dict:
    return {
        "task": "Produce one ExitGuide demo workflow result for this case.",
        "case_number": case["case_number"],
        "user_goal": case["user_goal"],
        "screen_context": case["screen_context"],
        "visible_screen_text": case["visible_screen_text"],
        "consumer_reference_case": {
            "product": case["product"],
            "category": case["category"],
            "question": compact(case["question"], 1200),
            "answer": compact(case["answer"], 1600),
        },
    }


def build_request(case: dict) -> dict:
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(build_user_payload(case), ensure_ascii=False, indent=2)},
        ],
        "temperature": 0.1,
        "max_tokens": 1400,
    }


def call_upstage(request_body: dict) -> dict:
    url = f"{API_BASE}/chat/completions"
    data = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_message_text(response: dict) -> str:
    try:
        return response["choices"][0]["message"]["content"]
    except Exception:
        return json.dumps(response, ensure_ascii=False)


def try_parse_json(text: str):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, items: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def write_report(path: Path, status: str, selected_cases: list[dict], outputs: list[dict]) -> None:
    lines = [
        "# Solar Demo Workflow",
        "",
        f"- Status: `{status}`",
        f"- Model: `{MODEL}`",
        f"- Source CSV: `{SOURCE_CSV}`",
        f"- Cases: {len(selected_cases)}",
        f"- Generated at: {now()}",
        "",
        "## Selected Cases",
        "",
        "| Case | Product | Category | Goal |",
        "| --- | --- | --- | --- |",
    ]
    for case in selected_cases:
        lines.append(
            f"| `{case['case_number']}` | {case['product']} | {case['category']} | {case['user_goal']} |"
        )
    lines.extend(["", "## Output Status", ""])
    if status == "completed":
        lines.append("| Case | Solar status | Parsed JSON |")
        lines.append("| --- | --- | --- |")
        for output in outputs:
            lines.append(
                f"| `{output['case_number']}` | `{output['status']}` | `{bool(output.get('parsed_json'))}` |"
            )
    else:
        lines.append("Solar API was not called because `UPSTAGE_API_KEY` was not available in the process environment or repo `.env`.")
        lines.append("")
        lines.append("Set `UPSTAGE_API_KEY` and rerun:")
        lines.append("")
        lines.append("```powershell")
        lines.append(".\\scripts\\Run-SolarDemoWorkflow.ps1")
        lines.append("```")
    lines.append("")
    lines.append("Generated files:")
    lines.append("")
    lines.append("- `selected_cases.json`")
    lines.append("- `agent_prompt.md`")
    lines.append("- `solar_requests.jsonl`")
    if status == "completed":
        lines.append("- `solar_outputs.jsonl`")
        lines.append("- `demo_fixture_candidates.json`")
        lines.append("- `workflow_outputs.md`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_fixture_candidates(path: Path, selected_cases: list[dict], outputs: list[dict]) -> None:
    case_by_number = {case["case_number"]: case for case in selected_cases}
    candidates = []
    for output in outputs:
        parsed = output.get("parsed_json")
        if not isinstance(parsed, dict):
            continue
        case = case_by_number.get(output["case_number"], {})
        candidates.append({
            "case_number": output["case_number"],
            "source": {
                "dataset": "data_go_kr_kca_standard_answers",
                "product": case.get("product"),
                "category": case.get("category"),
            },
            "demo_input": {
                "user_goal": case.get("user_goal"),
                "screen_context": case.get("screen_context"),
                "visible_screen_text": case.get("visible_screen_text", []),
            },
            "solar_result": parsed,
            "model": output.get("model"),
            "usage": output.get("usage"),
        })
    write_json(path, {
        "schema_version": "2026-07-08.1",
        "generated_at": now(),
        "model": MODEL,
        "candidates": candidates,
    })


def write_outputs_markdown(path: Path, outputs: list[dict]) -> None:
    lines = [
        "# Solar Workflow Outputs",
        "",
        "| Case | Risk | Confidence | Primary Action |",
        "| --- | --- | --- | --- |",
    ]
    for output in outputs:
        parsed = output.get("parsed_json") or {}
        action = parsed.get("recommended_action") or {}
        lines.append(
            f"| `{output.get('case_number')}` | `{parsed.get('risk_level', 'n/a')}` | `{parsed.get('confidence', 'n/a')}` | {action.get('primary', '')} |"
        )
    lines.append("")
    lines.append("## Details")
    for output in outputs:
        parsed = output.get("parsed_json") or {}
        lines.extend([
            "",
            f"### Case {output.get('case_number')}",
            "",
            f"- Risk: `{parsed.get('risk_level', 'n/a')}`",
            f"- Confidence: `{parsed.get('confidence', 'n/a')}`",
            f"- Screen summary: {parsed.get('screen_summary', '')}",
            "",
            "Goal conflicts:",
        ])
        for conflict in parsed.get("goal_conflicts") or []:
            lines.append(
                f"- `{conflict.get('risk_signal', 'needs_check')}`: {conflict.get('screen_text', '')} - {conflict.get('why_it_matters', '')}"
            )
        action = parsed.get("recommended_action") or {}
        lines.extend([
            "",
            "Recommended action:",
            f"- Primary: {action.get('primary', '')}",
            f"- Avoid: {action.get('avoid', '')}",
        ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    rows = read_kca_csv(SOURCE_CSV)
    selected_cases = select_cases(rows, MAX_CASES)
    requests = [
        {
            "case_number": case["case_number"],
            "request_sha256": hashlib.sha256(json.dumps(build_request(case), ensure_ascii=False).encode("utf-8")).hexdigest(),
            "request": build_request(case),
        }
        for case in selected_cases
    ]

    write_json(OUTPUT_ROOT / "selected_cases.json", selected_cases)
    (OUTPUT_ROOT / "agent_prompt.md").write_text(SYSTEM_PROMPT, encoding="utf-8")
    write_jsonl(OUTPUT_ROOT / "solar_requests.jsonl", requests)

    outputs = []
    if API_KEY:
        for item in requests:
            case_number = item["case_number"]
            started_at = now()
            try:
                response = call_upstage(item["request"])
                text = extract_message_text(response)
                outputs.append({
                    "case_number": case_number,
                    "status": "completed",
                    "started_at": started_at,
                    "finished_at": now(),
                    "raw_text": text,
                    "parsed_json": try_parse_json(text),
                    "usage": response.get("usage"),
                    "model": response.get("model"),
                })
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")[:1000]
                outputs.append({
                    "case_number": case_number,
                    "status": "failed",
                    "started_at": started_at,
                    "finished_at": now(),
                    "error": f"HTTP {exc.code}: {body}",
                })
            except Exception as exc:
                outputs.append({
                    "case_number": case_number,
                    "status": "failed",
                    "started_at": started_at,
                    "finished_at": now(),
                    "error": str(exc),
                })
            time.sleep(0.2)
        write_jsonl(OUTPUT_ROOT / "solar_outputs.jsonl", outputs)
        write_fixture_candidates(OUTPUT_ROOT / "demo_fixture_candidates.json", selected_cases, outputs)
        write_outputs_markdown(OUTPUT_ROOT / "workflow_outputs.md", outputs)
        status = "completed" if all(item["status"] == "completed" for item in outputs) else "partial"
    else:
        status = "blocked_missing_upstage_key"

    write_report(OUTPUT_ROOT / "workflow_report.md", status, selected_cases, outputs)
    print(f"status={status}")
    print(f"output={OUTPUT_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$env:PYTHONDONTWRITEBYTECODE = "1"
if ($ApiKey) {
  $env:UPSTAGE_API_KEY_FOR_WORKFLOW = $ApiKey
} else {
  Remove-Item Env:UPSTAGE_API_KEY_FOR_WORKFLOW -ErrorAction SilentlyContinue
}
$TempScriptPath = Join-Path $OutputRoot "run_solar_demo_workflow.py"
[System.IO.File]::WriteAllText($TempScriptPath, $Script, [System.Text.UTF8Encoding]::new($false))
& $Python $TempScriptPath $SourceCsvPath $OutputRoot $Model $MaxCases $HttpTimeoutSeconds
if ($LASTEXITCODE -ne 0) {
  throw "Solar demo workflow failed with exit code $LASTEXITCODE"
}
