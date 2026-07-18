from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evidence_schema import EvidenceRecord
from graphrag.context_builder import ContextBuilder
from graphrag.subgraph_retriever import SubgraphRetriever
from knowledge_graph.evidence_loader import load_evidence_records


SAMPLE = {
    "evidence_id": "official-hypertension-1",
    "disease": "高血压",
    "predicate": "prevent",
    "claim": "每日食盐摄入量逐步降至5克以下。",
    "source_name": "高血压指导原则",
    "source_url": "https://www.nhc.gov.cn/example.pdf",
    "publisher": "国家卫生健康委员会",
    "document_title": "高血压指导原则",
    "published_at": "2024-06-17",
    "accessed_at": "2026-07-18",
    "evidence_level": "official_guidance",
    "review_status": "source_verified",
    "section": "营养指导",
    "locator": "第4页",
}


class FakeGraph:
    def __init__(self, rows):
        self.rows = rows
        self.last_cypher = ""
        self.last_params = {}

    def run(self, cypher, **kwargs):
        self.last_cypher = cypher
        self.last_params = kwargs
        rows = self.rows

        class Result:
            def data(self):
                return rows

        return Result()


class CuratedEvidenceTests(unittest.TestCase):
    def test_schema_rejects_non_https_source(self) -> None:
        invalid = {**SAMPLE, "source_url": "http://example.test/source"}
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            EvidenceRecord.from_dict(invalid)

    def test_repository_hypertension_sample_is_valid(self) -> None:
        path = Path(__file__).parents[1] / "data" / "evidence" / "hypertension.jsonl"
        records = load_evidence_records(path)
        self.assertEqual(len(records), 5)
        self.assertTrue(all(record.disease == "高血压" for record in records))
        self.assertTrue(all(record.review_status == "source_verified" for record in records))

    def test_loader_rejects_duplicate_ids(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "evidence.jsonl"
            line = json.dumps(SAMPLE, ensure_ascii=False)
            path.write_text(f"{line}\n{line}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate evidence_id"):
                load_evidence_records(path)

    def test_curated_claim_replaces_legacy_property_in_context(self) -> None:
        subgraph = {
            "entities_found": ["高血压"],
            "nodes": [{
                "name": "高血压",
                "label": "Disease",
                "properties": {"prevent": "旧互联网饮食建议"},
                "evidence": {"evidence_level": "legacy_unverified"},
            }],
            "edges": [],
            "evidence_claims": [{
                **SAMPLE,
                "updated_at": SAMPLE["published_at"],
            }],
        }
        result = ContextBuilder().build(subgraph)
        self.assertIn("每日食盐摄入量逐步降至5克以下", result["context_text"])
        self.assertNotIn("旧互联网饮食建议", result["context_text"])
        self.assertEqual(result["evidence_items"][0]["kind"], "claim")
        self.assertEqual(result["evidence_items"][0]["citation_index"], 1)

    def test_retriever_filters_curated_claims_by_requested_fields(self) -> None:
        graph = FakeGraph([{**SAMPLE, "updated_at": SAMPLE["published_at"]}])
        retriever = SubgraphRetriever(graph=graph)
        rows = retriever._query_evidence_claims("高血压", ["prevent"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(graph.last_params["predicates"], ["prevent"])
        self.assertIn("HAS_EVIDENCE", graph.last_cypher)


if __name__ == "__main__":
    unittest.main()
