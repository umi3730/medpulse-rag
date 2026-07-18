from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.run_evaluation import aggregate, load_cases, score_response


class EvaluationTests(unittest.TestCase):
    def test_load_cases_rejects_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cases.jsonl"
            path.write_text(
                '\n'.join([
                    json.dumps({"id": "same", "question": "问题一"}),
                    json.dumps({"id": "same", "question": "问题二"}),
                ]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate id"):
                load_cases(path)

    def test_score_response_uses_only_configured_metrics(self) -> None:
        case = {
            "id": "case-1",
            "question": "高血压有什么症状？",
            "expected": {
                "requires_evidence": False,
                "intents": ["symptom"],
                "entities": {"disease": ["高血压"]},
                "relation_filters": ["has_symptom"],
                "answer_keywords": ["症状"],
                "forbidden_terms": ["保证治愈"],
            },
        }
        response = {
            "answer": "常见症状需要结合个体情况判断。",
            "debug": {
                "intents": ["symptom"],
                "entities_normalized": {"disease": ["高血压"]},
                "relation_filters": ["has_symptom"],
            },
        }
        result = score_response(case, response)
        self.assertEqual(result["overall"], 1.0)

    def test_aggregate_tracks_failed_requests(self) -> None:
        summary = aggregate([
            {"overall": 1.0, "metrics": {"entity_recall": 1.0}},
            {"overall": 0.0, "metrics": {}, "request_error": "offline"},
        ])
        self.assertEqual(summary["successful_requests"], 1)
        self.assertEqual(summary["failed_requests"], 1)
        self.assertEqual(summary["overall"], 1.0)

    def test_style_template_language_is_rejected(self) -> None:
        result = score_response(
            {"id": "style", "question": "高血压是什么？", "expected": {}},
            {"answer": "您好，根据知识图谱，高血压是一种疾病。", "debug": {}},
        )
        self.assertEqual(result["metrics"]["style_template_pass"], 0.0)

    def test_evidence_metadata_is_scored(self) -> None:
        result = score_response(
            {"id": "evidence", "question": "病因？", "expected": {}},
            {
                "answer": "糖尿病可能与遗传因素有关 [1]。",
                "debug": {},
                "evidence": [{
                    "citation_index": 1,
                    "subject": "糖尿病",
                    "predicate": "cause",
                    "object": "遗传因素",
                    "source_name": "测试来源",
                    "updated_at": "unknown",
                    "evidence_level": "legacy_unverified",
                }],
            },
        )
        self.assertEqual(result["metrics"]["evidence_present"], 1.0)
        self.assertEqual(result["metrics"]["evidence_metadata_complete"], 1.0)
        self.assertEqual(result["metrics"]["citation_validity"], 1.0)
        self.assertEqual(result["metrics"]["citation_completeness"], 1.0)
        self.assertEqual(result["metrics"]["citation_faithfulness"], 1.0)
        self.assertEqual(result["metrics"]["unsupported_claim_pass"], 1.0)

    def test_uncited_medical_claim_is_rejected(self) -> None:
        result = score_response(
            {"id": "uncited", "question": "症状？", "expected": {}},
            {
                "answer": "高血压可能出现头痛。",
                "debug": {},
                "evidence": [{
                    "citation_index": 1,
                    "subject": "高血压",
                    "predicate": "has_symptom",
                    "object": "头痛",
                    "source_name": "测试",
                    "updated_at": "2026-07-18",
                    "evidence_level": "reviewed_reference",
                }],
            },
        )
        self.assertEqual(result["metrics"]["citation_completeness"], 0.0)
        self.assertEqual(result["metrics"]["unsupported_claim_pass"], 0.0)

    def test_citation_range_is_expanded_and_validated(self) -> None:
        evidence = [
            {
                "citation_index": index,
                "subject": "感冒",
                "predicate": "common_drug",
                "object": f"药物{index}",
                "source_name": "测试",
                "updated_at": "2026-07-18",
                "evidence_level": "reviewed_reference",
            }
            for index in range(1, 4)
        ]
        result = score_response(
            {"id": "range", "question": "用药？", "expected": {}},
            {"answer": "常见药物包括药物1、药物2和药物3 [1]-[3]。", "debug": {}, "evidence": evidence},
        )
        self.assertEqual(result["debug"]["citations"], [1, 2, 3])
        self.assertEqual(result["metrics"]["citation_validity"], 1.0)

    def test_query_plan_controls_are_scored_when_expected(self) -> None:
        result = score_response(
            {
                "id": "plan-controls",
                "question": "请简单说说这个病",
                "expected": {
                    "detail_level": "brief",
                    "risk_level": "low",
                    "needs_clarification": True,
                    "requires_evidence": False,
                },
            },
            {
                "answer": "请先说明具体疾病名称。",
                "debug": {
                    "detail_level": "brief",
                    "risk_level": "low",
                    "needs_clarification": True,
                },
            },
        )
        self.assertEqual(result["metrics"]["detail_level_match"], 1.0)
        self.assertEqual(result["metrics"]["risk_level_match"], 1.0)
        self.assertEqual(result["metrics"]["clarification_match"], 1.0)

    def test_answer_keyword_groups_accept_synonyms(self) -> None:
        result = score_response(
            {
                "id": "synonyms",
                "question": "肺炎治疗多久？",
                "expected": {
                    "requires_evidence": False,
                    "answer_keyword_groups": [["时间", "周期", "疗程", "天"]],
                },
            },
            {"answer": "通常需要7至10天。", "debug": {}},
        )
        self.assertEqual(result["metrics"]["answer_keyword_recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
