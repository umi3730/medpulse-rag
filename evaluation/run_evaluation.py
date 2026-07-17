#!/usr/bin/env python3
"""Run deterministic GraphRAG evaluations against the MedPulse HTTP API."""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(__file__).with_name("cases.jsonl")
STYLE_FORBIDDEN_TERMS = (
    "您好",
    "根据知识图谱",
    "根据提供的信息",
    "以上信息仅供参考，具体请咨询专业医生",
)


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            case_id = case.get("id")
            question = case.get("question")
            if not isinstance(case_id, str) or not case_id.strip():
                raise ValueError(f"{path}:{line_number}: id must be a non-empty string")
            if case_id in seen_ids:
                raise ValueError(f"{path}:{line_number}: duplicate id {case_id!r}")
            if not isinstance(question, str) or not question.strip():
                raise ValueError(f"{path}:{line_number}: question must be a non-empty string")
            seen_ids.add(case_id)
            cases.append(case)
    if not cases:
        raise ValueError(f"{path}: dataset contains no cases")
    return cases


def _recall(expected: set[str], actual: set[str]) -> float | None:
    if not expected:
        return None
    return len(expected & actual) / len(expected)


def _flatten_entities(entities: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for names in entities.values():
        if isinstance(names, list):
            values.update(str(name).strip() for name in names if str(name).strip())
    return values


def score_response(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected", {})
    debug = response.get("debug") or {}
    answer = str(response.get("answer") or "")
    evidence = response.get("evidence") or []

    expected_intents = set(expected.get("intents", []))
    actual_intents = set(debug.get("intents") or [])
    expected_relations = set(expected.get("relation_filters", []))
    actual_relations = set(debug.get("relation_filters") or [])
    expected_fields = set(expected.get("requested_fields", []))
    actual_fields = set(debug.get("requested_fields") or [])
    expected_entities = {
        str(name)
        for names in (expected.get("entities") or {}).values()
        for name in names
    }
    actual_entities = _flatten_entities(debug.get("entities_normalized") or {})
    answer_keywords = [str(keyword) for keyword in expected.get("answer_keywords", [])]
    answer_keyword_groups = [
        [str(keyword) for keyword in group]
        for group in expected.get("answer_keyword_groups", [])
        if group
    ]
    forbidden_terms = [str(term) for term in expected.get("forbidden_terms", [])]

    def exact_match(name: str, actual: Any) -> float | None:
        return float(actual == expected[name]) if name in expected else None

    metrics: dict[str, float | None] = {
        "intent_recall": _recall(expected_intents, actual_intents),
        "entity_recall": _recall(expected_entities, actual_entities),
        "relation_recall": _recall(expected_relations, actual_relations),
        "requested_field_recall": _recall(expected_fields, actual_fields),
        "answer_keyword_recall": (
            (
                sum(keyword in answer for keyword in answer_keywords)
                + sum(any(keyword in answer for keyword in group) for group in answer_keyword_groups)
            ) / (len(answer_keywords) + len(answer_keyword_groups))
            if answer_keywords or answer_keyword_groups else None
        ),
        "forbidden_term_pass": (
            float(not any(term in answer for term in forbidden_terms))
            if forbidden_terms else None
        ),
        "style_template_pass": float(
            not any(term in answer for term in STYLE_FORBIDDEN_TERMS)
        ),
        "evidence_present": (
            float(bool(evidence)) if expected.get("requires_evidence", True) else None
        ),
        "evidence_metadata_complete": (
            sum(
                bool(item.get("source_name"))
                and bool(item.get("updated_at"))
                and bool(item.get("evidence_level"))
                for item in evidence
            ) / len(evidence)
            if evidence else None
        ),
        "detail_level_match": exact_match(
            "detail_level", debug.get("detail_level", "standard")
        ),
        "risk_level_match": exact_match(
            "risk_level", debug.get("risk_level", "low")
        ),
        "clarification_match": exact_match(
            "needs_clarification", bool(debug.get("needs_clarification", False))
        ),
    }
    scored_values = [value for value in metrics.values() if value is not None]
    overall = statistics.fmean(scored_values) if scored_values else 0.0
    return {
        "id": case["id"],
        "question": case["question"],
        "answer": answer,
        "metrics": metrics,
        "overall": round(overall, 4),
        "debug": {
            "intents": sorted(actual_intents),
            "entities": sorted(actual_entities),
            "relation_filters": sorted(actual_relations),
            "requested_fields": sorted(actual_fields),
            "detail_level": debug.get("detail_level", "standard"),
            "needs_clarification": debug.get("needs_clarification", False),
            "risk_level": debug.get("risk_level", "low"),
            "retrieval_mode": debug.get("retrieval_mode", "none"),
            "subgraph_stats": debug.get("subgraph_stats", {}),
            "total_time_ms": debug.get("total_time_ms", 0),
            "error": debug.get("error", ""),
            "evidence_count": len(evidence),
        },
    }


def request_case(
    case: dict[str, Any], base_url: str, timeout: float, run_id: str
) -> dict[str, Any]:
    identity = {
        "user_id": f"eval_{run_id}",
        "session_id": f"case_{case['id'].replace('-', '_')}",
    }

    def send(question: str) -> dict[str, Any]:
        payload = json.dumps({"question": question, **identity}).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/graphrag/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    for history_question in case.get("history", []):
        send(str(history_question))
    return send(case["question"])


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    metric_names = sorted({
        name for result in results for name in result.get("metrics", {})
    })
    metrics: dict[str, float | None] = {}
    for name in metric_names:
        values = [
            result["metrics"][name]
            for result in results
            if result["metrics"].get(name) is not None
        ]
        metrics[name] = round(statistics.fmean(values), 4) if values else None
    successful = [result for result in results if not result.get("request_error")]
    return {
        "case_count": len(results),
        "successful_requests": len(successful),
        "failed_requests": len(results) - len(successful),
        "overall": round(statistics.fmean(r["overall"] for r in successful), 4)
        if successful else 0.0,
        "metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("evaluation/results/latest.json"))
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Run only the selected case ID; repeat this option for multiple cases.",
    )
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    cases = load_cases(args.dataset)
    print(f"Validated {len(cases)} evaluation cases from {args.dataset}")
    if args.case_ids:
        selected = set(args.case_ids)
        known = {case["id"] for case in cases}
        unknown = sorted(selected - known)
        if unknown:
            parser.error(f"unknown case ID(s): {', '.join(unknown)}")
        cases = [case for case in cases if case["id"] in selected]
        print(f"Selected {len(cases)} case(s): {', '.join(case['id'] for case in cases)}")
    if args.validate_only:
        return 0

    run_id = str(int(time.time()))
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['id']}: {case['question']}")
        try:
            response = request_case(case, args.base_url, args.timeout, run_id)
            results.append(score_response(case, response))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            results.append({
                "id": case["id"],
                "question": case["question"],
                "answer": "",
                "metrics": {},
                "overall": 0.0,
                "request_error": str(exc),
            })

    report = {
        "dataset": str(args.dataset),
        "base_url": args.base_url,
        "run_id": run_id,
        "summary": aggregate(results),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Report written to {args.output}")
    return 1 if report["summary"]["failed_requests"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
