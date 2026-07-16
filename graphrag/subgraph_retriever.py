#!/usr/bin/env python3
# coding: utf-8
"""
多跳子图检索器：围绕抽取到的实体，从 Neo4j 动态检索 1-2 跳子图。
"""
from __future__ import annotations

import logging
import time

from neo4j_client import Neo4jGraph as Graph

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
                 relation_filters: list[str] | None = None) -> dict:
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
            rows = self._query_neighbors(entity_name, HOP1_LIMIT, relation_filters)
            for row in rows:
                self._add_to_graph(row, nodes_map, edges_list, seen_edges)
            self._fetch_disease_properties(entity_name, nodes_map)

        # ---- Hop 2: 邻居的邻居 ----
        if max_hops >= 2:
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
                    self._fetch_disease_properties(node_name, nodes_map)

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
            "type(r) AS r_type, labels(m)[0] AS m_label, m.name AS m_name "
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

    def _fetch_disease_properties(self, name: str, nodes_map: dict):
        """获取 Disease 节点的丰富属性。"""
        node = nodes_map.get(name)
        if not node or node.get("label") != "Disease":
            return
        if node.get("properties"):
            return  # 已获取过

        props_clause = ", ".join(f"n.{p} AS {p}" for p in DISEASE_PROPERTIES)
        cypher = f"MATCH (n:Disease) WHERE n.name = $name RETURN {props_clause}"
        try:
            rows = self.graph.run(cypher, name=name).data()
            if rows:
                props = {k: v for k, v in rows[0].items() if v}
                nodes_map[name]["properties"] = props
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

        if n_name and n_name not in nodes_map:
            nodes_map[n_name] = {"name": n_name, "label": n_label, "properties": {}}
        if m_name and m_name not in nodes_map:
            nodes_map[m_name] = {"name": m_name, "label": m_label, "properties": {}}

        edge_key = f"{n_name}-{r_type}-{m_name}"
        reverse_key = f"{m_name}-{r_type}-{n_name}"
        if edge_key not in seen_edges and reverse_key not in seen_edges:
            seen_edges.add(edge_key)
            edges_list.append({
                "source": n_name, "source_label": n_label,
                "target": m_name, "target_label": m_label,
                "relationship": r_type,
            })
