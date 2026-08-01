from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / ".artifacts" / "demo-report.md"


def main() -> None:
    client = TestClient(app)
    scenarios = client.get("/v1/demo-scenarios").json()
    demo_flows = client.get("/v1/demo-flows").json()
    synthetic_catalog = client.get("/v1/synthetic-screens").json()
    readiness = client.get("/v1/readiness").json()
    quality_response = client.get("/v1/demo-quality")
    quality_response.raise_for_status()
    quality = quality_response.json()
    consent_quality_response = client.get("/v1/consent-cases/quality")
    consent_quality_response.raise_for_status()
    consent_quality = consent_quality_response.json()
    prompt_preview = client.post(
        "/v1/prompt/demo",
        json={"goal_id": "buy_without_addons", "scenario_id": "checkout_addons"},
    )
    prompt_preview.raise_for_status()
    prompt_payload = prompt_preview.json()
    expected_risk_by_filename = {
        screen["filename"]: screen["risk_fixture"]
        for screen in synthetic_catalog["screens"]
    }
    readiness_passed = sum(1 for check in readiness["checks"] if check["passed"])
    readiness_total = len(readiness["checks"])
    scenario_mismatches: list[str] = []
    synthetic_mismatches: list[str] = []

    lines = [
        "# ExitGuide Demo Report",
        "",
        "Generated from deterministic API demo scenarios.",
        f"Synthetic fixture pack: {synthetic_catalog['screen_count']} screens.",
        f"Prompt preview: system {len(prompt_payload['system_prompt'])} chars, user {len(prompt_payload['user_prompt'])} chars.",
        f"Readiness: {readiness['status']} ({sum(1 for check in readiness['checks'] if check['passed'])}/{len(readiness['checks'])} checks passed).",
        f"Quality endpoint: {quality['status']} ({quality['summary']['scenarios_passed']}/{quality['summary']['scenarios_total']} scenarios, {quality['summary']['flows_passed']}/{quality['summary']['flows_total']} flows, {quality['summary']['synthetic_passed']}/{quality['summary']['synthetic_total']} synthetic fixtures).",
        f"Consent case quality: {consent_quality['status']} ({consent_quality['evaluation_scope']}; {sum(1 for item in consent_quality['calibrations'] if item['passed'])}/{len(consent_quality['calibrations'])} cases).",
        f"Consent case coverage: {consent_quality['coverage']['status']} ({sum(1 for item in consent_quality['coverage']['targets'] if item['passed'])}/{len(consent_quality['coverage']['targets'])} targets).",
        "Consent case quality is deterministic rule calibration only; it does not measure OCR extraction, live provider reasoning, or end-to-end mobile accuracy.",
        "",
    ]

    for scenario in scenarios:
        response = client.post(
            "/v1/analyze/demo",
            json={
                "goal_id": scenario["recommended_goal_id"],
                "scenario_id": scenario["id"],
            },
        )
        response.raise_for_status()
        analysis = response.json()
        expected_risk = expected_risk_by_filename.get(scenario["fixture_filename"], "n/a")
        actual_risk = analysis["overall_risk"]
        risk_status = "OK" if expected_risk == actual_risk else "MISMATCH"
        if risk_status != "OK":
            scenario_mismatches.append(
                f"{scenario['id']}: expected {expected_risk}, got {actual_risk}"
            )
        lines.extend(
            [
                f"## {scenario['label']}",
                "",
                f"- Analysis ID: `{analysis['analysis_id']}`",
                f"- Goal: {analysis['goal_label']}",
                f"- Screen: {analysis['screen_title']}",
                f"- Expected fixture risk: {expected_risk}",
                f"- Overall risk: {actual_risk}",
                f"- Risk match: {risk_status}",
                f"- Goal alignment: {analysis['alignment_score']}/100",
                f"- Recommended action: {analysis['recommended_action']['description']}",
                "- Evidence:",
            ]
        )
        lines.extend(f"  - {evidence}" for evidence in analysis["proof_card"]["key_evidence"])
        lines.append("")

    for flow_definition in demo_flows:
        flow_response = client.post(
            "/v1/analyze/flow",
            json={
                "goal_id": flow_definition["goal_id"],
                "scenario_ids": flow_definition["scenario_ids"],
            },
        )
        flow_response.raise_for_status()
        flow = flow_response.json()
        lines.extend(
            [
                f"## Flow Check: {flow_definition['label']}",
                "",
                f"- Flow ID: `{flow['flow_id']}`",
                f"- Goal: {flow['goal_label']}",
                f"- Overall risk: {flow['overall_risk']}",
                f"- Flow alignment: {flow['alignment_score']}/100",
                f"- Screens: {flow['screen_count']}",
                f"- Highest-risk screen: {flow['highest_risk_screen_number']}",
                f"- Flow risk counts: {flow['risk_counts']['high']} high, {flow['risk_counts']['medium']} medium, {flow['risk_counts']['low']} low",
                f"- Risk path: {' -> '.join(flow['risk_path'])}",
                f"- Summary: {flow['summary']}",
                "- Evidence:",
            ]
        )
        lines.extend(f"  - {evidence}" for evidence in flow["proof_card"]["key_evidence"])
        lines.append("")

    lines.extend(
        [
            "## Synthetic Upload Calibration",
            "",
            "| File | Goal | Expected | Actual | Alignment | Status |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for screen in synthetic_catalog["screens"]:
        goal_id = screen["recommended_goal_id"]
        upload_response = client.post(
            "/v1/analyze",
            data={"goal_id": goal_id},
            files={"screenshot": (screen["filename"], b"fake", "image/png")},
        )
        upload_response.raise_for_status()
        analysis = upload_response.json()
        actual_risk = analysis["overall_risk"]
        risk_status = "OK" if actual_risk == screen["risk_fixture"] else "MISMATCH"
        if risk_status != "OK":
            synthetic_mismatches.append(
                f"{screen['filename']}: expected {screen['risk_fixture']}, got {actual_risk}"
            )
        lines.append(
            f"| `{screen['filename']}` | `{goal_id}` | {screen['risk_fixture']} | {actual_risk} | {analysis['alignment_score']}/100 | {risk_status} |"
        )
    lines.append("")

    quality_failures: list[str] = []
    if quality["status"] != "pass":
        quality_failures.append(f"demo quality endpoint is {quality['status']}")
    if consent_quality["status"] != "pass":
        quality_failures.append(f"consent case quality endpoint is {consent_quality['status']}")
    if consent_quality["coverage"]["warnings"]:
        quality_failures.extend(f"consent case coverage warning: {warning}" for warning in consent_quality["coverage"]["warnings"])
    if readiness["status"] != "ready":
        quality_failures.append(f"readiness is {readiness['status']}")
    quality_failures.extend(scenario_mismatches)
    quality_failures.extend(synthetic_mismatches)

    lines.extend(
        [
            "## Quality Gate",
            "",
            f"- Readiness: {'OK' if readiness['status'] == 'ready' else 'MISMATCH'} ({readiness_passed}/{readiness_total} checks passed)",
            f"- API quality endpoint: {'OK' if quality['status'] == 'pass' else 'MISMATCH'}",
            f"- Scenario risk calibration: {len(scenarios) - len(scenario_mismatches)}/{len(scenarios)} matched",
            f"- Flow risk path calibration: {quality['summary']['flows_passed']}/{quality['summary']['flows_total']} matched",
            f"- Synthetic upload calibration: {len(synthetic_catalog['screens']) - len(synthetic_mismatches)}/{len(synthetic_catalog['screens'])} matched",
            f"- Consent case rule calibration: {sum(1 for item in consent_quality['calibrations'] if item['passed'])}/{len(consent_quality['calibrations'])} matched",
            f"- Consent case coverage: {sum(1 for item in consent_quality['coverage']['targets'] if item['passed'])}/{len(consent_quality['coverage']['targets'])} targets",
            f"- Consent case risk coverage: low {consent_quality['summary']['risk_counts'].get('low', 0)}, medium {consent_quality['summary']['risk_counts'].get('medium', 0)}, high {consent_quality['summary']['risk_counts'].get('high', 0)}",
            f"- Consent case scope: {consent_quality['evaluation_scope']} (not evaluated: {', '.join(consent_quality['not_evaluated'])})",
            f"- Result: {'PASS' if not quality_failures else 'FAIL'}",
            "",
        ]
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")

    if quality_failures:
        raise AssertionError("Demo report quality gate failed: " + "; ".join(quality_failures))


if __name__ == "__main__":
    main()
