from __future__ import annotations

import unittest

from graphrag.subgraph_retriever import SubgraphRetriever


class _Result:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def data(self) -> list[dict]:
        return self._rows


class _Graph:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.queries: list[str] = []

    def run(self, query: str, **kwargs):
        self.queries.append(query)
        self.calls.append(kwargs)
        name = kwargs["name"]
        return _Result([
            {
                "n_name": name,
                "n_label": "Disease",
                "r_type": "common_drug",
                "m_name": f"{name}-药物",
                "m_label": "Drug",
            }
        ])


class SubgraphRetrieverTests(unittest.TestCase):
    def test_relation_filtered_retrieval_does_not_expand_hop_two(self) -> None:
        graph = _Graph()
        result = SubgraphRetriever(graph=graph).retrieve(
            {"disease": ["感冒"]},
            max_hops=2,
            relation_filters=["common_drug"],
            property_filters=["common_drug"],
        )
        self.assertEqual(len(graph.calls), 1)
        self.assertEqual(result["stats"]["effective_max_hops"], 1)
        self.assertEqual(result["stats"]["total_edges"], 1)

    def test_legacy_metadata_uses_dynamic_property_access(self) -> None:
        graph = _Graph()
        retriever = SubgraphRetriever(graph=graph)

        retriever._query_neighbors("高血压", 10)
        retriever._fetch_disease_properties("高血压", {}, ["prevent"])

        neighbor_query, property_query = graph.queries
        for alias in ("r", "n", "m"):
            self.assertIn(f"properties({alias})['updated_at']", neighbor_query)
            self.assertNotIn(f"{alias}.updated_at", neighbor_query)
        for key in ("source_name", "source_url", "updated_at", "evidence_level"):
            self.assertIn(f"properties(n)['{key}']", property_query)
            self.assertNotIn(f"n.{key}", property_query)
