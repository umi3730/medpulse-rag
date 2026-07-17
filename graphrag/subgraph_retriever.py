#!/usr/bin/env python3
# coding: utf-8
"""
多跳子图检索器：围绕抽取到的实体，从 Neo4j 动态检索 1-2 跳子图。
"""
from __future__ import annotations

import logging
import time

from neo4j_client import Neo4jGraph as Graph
from evidence_metadata import normalize_evidence_metadata

from .config import (
    NEO4J_URI, NEO4J_USER, NEO4J_DATABASE, NEO4J_PASSWORD,
    MAX_HOPS, HOP1_LIMIT, HOP2_LIMIT, HOP2_CANDIDATES,
    DISEASE_PROPERTIES,
)

log = logging.getLogger("graphrag")


class SubgraphRetriever:
    """从 Neo4j 检索实体周围的多跳子图。"""

    def __init__(self, graph: Graph | None = None):
        if graph:
            self.graph = graph
        else:
            self.graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), name=NEO4J_DATABASE)

    def retrieve(self, entity_dict: dict[str, list[str]],
                 max_hops: int = MAX_HOPS,
                 relation_filters: list[str] | None = None,
                 property_filters: list[str] | None = None,
                 include_neighbors: bool = True) -> dict:
        """
        检索子图。

        参数:
          entity_dict: {"disease": ["糖尿病"], "symptom": ["头痛"], ...}

        返回:
          {
            "entities_found": ["糖尿病", "头痛"],
            "nodes": [{"name": "...", "label": "...", "properties": {...}}, ...],
            "edges": [{"source": "...", "source_label": "...",
                       "target": "...", "target_label": "...",
                       "relationship": "..."}, ...],
            "stats": {"total_nodes": N, "total_edges": M, "retrieval_time_ms": T},
          }
        """
        t0 = time.time()
        all_entities = []
        for names in entity_dict.values():
            all_entities.extend(names)

        nodes_map: dict[str, dict] = {}  # name → {name, label, properties}
        edges_list: list[dict] = []
        seen_edges: set[str] = set()

        # ---- Hop 1: 直接邻居 ----
        for entity_name in all_entities:
            if include_neighbors:
                rows = self._query_neighbors(entity_name, HOP1_LIMIT, relation_filters)
                for row in rows:
                    self._add_to_graph(row, nodes_map, edges_list, seen_edges)
            self._fetch_disease_properties(entity_name, nodes_map, property_filters)

        # Intent-filtered relations (symptoms, drugs, checks, etc.) are direct
        # facts about the query entity. Expanding their targets adds unrelated
        # diseases and can multiply a small result into hundreds of edges.
        effective_max_hops = 1 if relation_filters else max_hops

        # ---- Hop 2: 邻居的邻居 ----
        if include_neighbors and effective_max_hops >= 2:
            hop1_names = [n for n in nodes_map if n not in all_entities]
            # 优先扩展 Disease 节点（信息最丰富）
            diseases = [n for n in hop1_names if nodes_map[n].get("label") == "Disease"]
            others = [n for n in hop1_names if nodes_map[n].get("label") != "Disease"]
            candidates = (diseases + others)[:HOP2_CANDIDATES]

            for node_name in candidates:
                rows = self._query_neighbors(node_name, HOP2_LIMIT, relation_filters)
                for row in rows:
                    self._add_to_graph(row, nodes_map, edges_list, seen_edges)
                if nodes_map.get(node_name, {}).get("label") == "Disease":
                    self._fetch_disease_properties(node_name, nodes_map, property_filters)

        elapsed = (time.time() - t0) * 1000
        return {
            "entities_found": all_entities,
            "nodes": list(nodes_map.values()),
            "edges": edges_list,
            "stats": {
                "total_nodes": len(nodes_map),
                "total_edges": len(edges_list),
                "retrieval_time_ms": round(elapsed, 1),
                "relation_filters": relation_filters or [],
                "property_filters": property_filters or [],
                "effective_max_hops": effective_max_hops,
            },
        }

    # ==================================================================
    # 内部查询方法
    # ==================================================================
    def _query_neighbors(self, name: str, limit: int,
                         relation_filters: list[str] | None = None) -> list[dict]:
        """通用邻居查询（双向）。"""
        rel_clause = " AND type(r) IN $relation_filters" if relation_filters else ""
        cypher = (
            "MATCH (n)-[r]-(m) WHERE n.name = $name "
            f"{rel_clause} "
            "RETURN labels(n)[0] AS n_label, n.name AS n_name, "
            "type(r) AS r_type, labels(m)[0] AS m_label, m.name AS m_name, "
            "coalesce(r.source_name, n.source_name, m.source_name) AS source_name, "
            "coalesce(r.source_url, n.source_url, m.source_url) AS source_url, "
            "coalesce(r.updated_at, n.updated_at, m.updated_at) AS updated_at, "
            "coalesce(r.evidence_level, n.evidence_level, m.evidence_level) AS evidence_level "
            "LIMIT $limit"
        )
        try:
            return self.graph.run(
                cypher,
                name=name,
                limit=limit,
                relation_filters=relation_filters or [],
            ).data()
        except Exception as e:
            log.error("邻居查询失败 [%s]: %s", name, e)
            return []

    def _fetch_disease_properties(
        self,
        name: str,
        nodes_map: dict,
        property_filters: list[str] | None = None,
    ):
        """获取 Disease 节点的丰富属性。"""
        node = nodes_map.get(name)
        if node and node.get("label") != "Disease":
            return
        if node and node.get("properties"):
            return  # 已获取过

        property_candidates = DISEASE_PROPERTIES if property_filters is None else property_filters
        properties = [
            prop for prop in property_candidates
            if prop in DISEASE_PROPERTIES
        ]
        if not properties:
            return
        props_clause = ", ".join(f"n.{p} AS {p}" for p in properties)
        cypher = (
            "MATCH (n:Disease) WHERE n.name = $name "
            f"RETURN n.name AS name, {props_clause}, "
            "n.source_name AS source_name, n.source_url AS source_url, "
            "n.updated_at AS updated_at, n.evidence_level AS evidence_level"
        )
        try:
            rows = self.graph.run(cypher, name=name).data()
            if rows:
                metadata_keys = {
                    "name", "source_name", "source_url", "updated_at", "evidence_level"
                }
                props = {
                    k: v for k, v in rows[0].items()
                    if k not in metadata_keys and v
                }
                node_data = nodes_map.setdefault(
                    name, {"name": name, "label": "Disease", "properties": {}}
                )
                node_data["properties"] = props
                node_data["evidence"] = normalize_evidence_metadata(rows[0])
        except Exception as e:
            log.error("属性查询失败 [%s]: %s", name, e)

    @staticmethod
    def _add_to_graph(row: dict, nodes_map: dict,
                      edges_list: list, seen_edges: set):
        """将一行查询结果添加到图数据中（去重）。"""
        n_name = row.get("n_name", "")
        m_name = row.get("m_name", "")
        n_label = row.get("n_label", "")
        m_label = row.get("m_label", "")
        r_type = row.get("r_type", "")
        evidence = normalize_evidence_metadata(row)

        if n_name and n_name not in nodes_map:
            nodes_map[n_name] = {
                "name": n_name,
                "label": n_label,
                "properties": {},
                "evidence": evidence,
            }
        if m_name and m_name not in nodes_map:
            nodes_map[m_name] = {
                "name": m_name,
                "label": m_label,
                "properties": {},
                "evidence": evidence,
            }

        edge_key = f"{n_name}-{r_type}-{m_name}"
        reverse_key = f"{m_name}-{r_type}-{n_name}"
        if edge_key not in seen_edges and reverse_key not in seen_edges:
            seen_edges.add(edge_key)
            edges_list.append({
                "source": n_name, "source_label": n_label,
                "target": m_name, "target_label": m_label,
                "relationship": r_type,
                "evidence": evidence,
            })
