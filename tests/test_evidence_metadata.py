from __future__ import annotations

import unittest

from evidence_metadata import normalize_evidence_metadata
from graphrag.context_builder import ContextBuilder
from graphrag.subgraph_retriever import SubgraphRetriever


class EvidenceMetadataTests(unittest.TestCase):
    def test_missing_metadata_uses_honest_legacy_defaults(self) -> None:
        metadata = normalize_evidence_metadata({})
        self.assertEqual(metadata["source_name"], "寻医问药网历史数据集")
        self.assertEqual(metadata["updated_at"], "unknown")
        self.assertEqual(metadata["evidence_level"], "legacy_unverified")

    def test_relation_row_gets_metadata_without_changing_path(self) -> None:
        nodes: dict = {}
        edges: list[dict] = []
        SubgraphRetriever._add_to_graph(
            {
                "n_name": "糖尿病",
                "n_label": "Disease",
                "r_type": "has_symptom",
                "m_name": "口渴",
                "m_label": "Symptom",
            },
            nodes,
            edges,
            set(),
        )
        self.assertEqual(edges[0]["source"], "糖尿病")
        self.assertEqual(edges[0]["target"], "口渴")
        self.assertEqual(edges[0]["evidence"]["evidence_level"], "legacy_unverified")

    def test_context_builder_emits_property_and_relation_evidence(self) -> None:
        metadata = {
            "source_name": "测试来源",
            "source_url": "https://example.test/source",
            "updated_at": "2026-07-16",
            "evidence_level": "reviewed_reference",
        }
        result = ContextBuilder().build({
            "entities_found": ["糖尿病"],
            "nodes": [
                {
                    "name": "糖尿病",
                    "label": "Disease",
                    "properties": {"cause": "测试病因"},
                    "evidence": metadata,
                },
                {
                    "name": "口渴",
                    "label": "Symptom",
                    "properties": {},
                    "evidence": metadata,
                },
            ],
            "edges": [{
                "source": "糖尿病",
                "source_label": "Disease",
                "target": "口渴",
                "target_label": "Symptom",
                "relationship": "has_symptom",
                "evidence": metadata,
            }],
        })
        items = result["evidence_items"]
        self.assertEqual({item["kind"] for item in items}, {"property", "relation"})
        self.assertTrue(all(item["source_name"] == "测试来源" for item in items))
        self.assertIn("证据元数据", result["context_text"])

    def test_relation_evidence_matches_context_target_limit(self) -> None:
        edges = [
            {
                "source": "感冒",
                "source_label": "Disease",
                "target": f"药物{i}",
                "target_label": "Drug",
                "relationship": "common_drug",
                "evidence": {},
            }
            for i in range(30)
        ]
        result = ContextBuilder().build({
            "entities_found": ["感冒"],
            "nodes": [
                {"name": "感冒", "label": "Disease", "properties": {}},
                *[
                    {"name": f"药物{i}", "label": "Drug", "properties": {}}
                    for i in range(30)
                ],
            ],
            "edges": edges,
        })
        relation_items = [
            item for item in result["evidence_items"] if item["kind"] == "relation"
        ]
        self.assertEqual(len(relation_items), 15)
        self.assertIn("共30项", result["context_text"])


if __name__ == "__main__":
    unittest.main()
