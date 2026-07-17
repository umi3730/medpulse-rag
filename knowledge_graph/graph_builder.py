#!/usr/bin/env python3
# coding: utf-8
"""
Neo4j 图谱构建器：批量创建节点、关系和索引。

使用参数化 Cypher + UNWIND 批量写入，替代原版逐条插入。
"""

import logging
from neo4j_client import Neo4jGraph as Graph

from config import (
    DEFAULT_EVIDENCE_LEVEL,
    DEFAULT_SOURCE_NAME,
    DEFAULT_SOURCE_URL,
    DEFAULT_UPDATED_AT,
    NEO4J_DATABASE,
    REL_TYPES,
)

log = logging.getLogger("kg")

# 每批写入的条数
BATCH_SIZE = 500


class GraphBuilder:
    """封装 Neo4j 写入操作。"""

    def __init__(self, uri, user, password, database=NEO4J_DATABASE):
        log.info("连接 Neo4j: %s (用户: %s, 数据库: %s)", uri, user, database)
        self.graph = Graph(uri, auth=(user, password), name=database)
        log.info("Neo4j 连接成功")

    # ==================================================================
    # 索引 / 约束
    # ==================================================================
    def create_indexes(self, labels):
        """为每个节点标签的 name 属性创建索引（如果不存在）。"""
        for label in labels:
            cypher = (
                f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.name)"
            )
            try:
                self.graph.run(cypher)
                log.info("索引已创建/已存在: %s(name)", label)
            except Exception as e:
                log.warning("创建索引 %s 失败: %s", label, e)

    # ==================================================================
    # 清空图谱
    # ==================================================================
    def clear_all(self):
        """删除所有节点和关系（慎用）。"""
        self.graph.run("MATCH (n) DETACH DELETE n")
        log.info("已清空图谱所有数据")

    # ==================================================================
    # 创建简单节点（Drug / Food / Check / Department / Producer / Symptom）
    # ==================================================================
    def create_simple_nodes(self, label, names):
        """批量创建只有 name 属性的节点。使用 MERGE 避免重复。"""
        names_list = list(names)
        total = len(names_list)
        created = 0
        for i in range(0, total, BATCH_SIZE):
            batch = names_list[i:i + BATCH_SIZE]
            cypher = (
                f"UNWIND $names AS item MERGE (n:{label} {{name: item}}) "
                "SET n.source_name = coalesce(n.source_name, $source_name), "
                "n.source_url = coalesce(n.source_url, $source_url), "
                "n.updated_at = coalesce(n.updated_at, $updated_at), "
                "n.evidence_level = coalesce(n.evidence_level, $evidence_level)"
            )
            self.graph.run(
                cypher,
                names=batch,
                source_name=DEFAULT_SOURCE_NAME,
                source_url=DEFAULT_SOURCE_URL,
                updated_at=DEFAULT_UPDATED_AT,
                evidence_level=DEFAULT_EVIDENCE_LEVEL,
            )
            created += len(batch)
            log.info("  [%s] %d / %d", label, created, total)
        log.info("节点创建完成: %s (%d)", label, total)

    # ==================================================================
    # 创建疾病节点（带多属性）
    # ==================================================================
    def create_disease_nodes(self, disease_infos):
        """批量创建 Disease 节点，携带属性。"""
        total = len(disease_infos)
        created = 0
        for i in range(0, total, BATCH_SIZE):
            batch = disease_infos[i:i + BATCH_SIZE]
            cypher = """
            UNWIND $batch AS d
            MERGE (n:Disease {name: d.name})
            SET n.desc           = d.desc,
                n.prevent        = d.prevent,
                n.cause          = d.cause,
                n.easy_get       = d.easy_get,
                n.cure_department = d.cure_department,
                n.cure_way       = d.cure_way,
                n.cure_lasttime  = d.cure_lasttime,
                n.cured_prob     = d.cured_prob,
                n.get_prob       = d.get_prob,
                n.yibao_status   = d.yibao_status,
                n.get_way        = d.get_way,
                n.cost_money     = d.cost_money,
                n.source_name    = d.source_name,
                n.source_url     = d.source_url,
                n.updated_at     = d.updated_at,
                n.evidence_level = d.evidence_level
            """
            self.graph.run(cypher, batch=batch)
            created += len(batch)
            log.info("  [Disease] %d / %d", created, total)
        log.info("节点创建完成: Disease (%d)", total)

    # ==================================================================
    # 创建关系
    # ==================================================================
    def create_relationships(self, rel_type, pairs):
        """
        批量创建关系。
        pairs: [(src_name, dst_name), ...]
        rel_type: 关系类型名（如 has_symptom）
        """
        if rel_type not in REL_TYPES:
            log.error("未知关系类型: %s", rel_type)
            return

        src_label, dst_label, rel_name = REL_TYPES[rel_type]
        total = len(pairs)
        if total == 0:
            return

        created = 0
        for i in range(0, total, BATCH_SIZE):
            batch = [{"src": p[0], "dst": p[1]} for p in pairs[i:i + BATCH_SIZE]]
            cypher = (
                "UNWIND $batch AS r "
                f"MATCH (p:{src_label} {{name: r.src}}) "
                f"MATCH (q:{dst_label} {{name: r.dst}}) "
                f"MERGE (p)-[rel:{rel_type} {{name: $rel_name}}]->(q) "
                "SET rel.source_name = coalesce(rel.source_name, $source_name), "
                "rel.source_url = coalesce(rel.source_url, $source_url), "
                "rel.updated_at = coalesce(rel.updated_at, $updated_at), "
                "rel.evidence_level = coalesce(rel.evidence_level, $evidence_level)"
            )
            self.graph.run(
                cypher,
                batch=batch,
                rel_name=rel_name,
                source_name=DEFAULT_SOURCE_NAME,
                source_url=DEFAULT_SOURCE_URL,
                updated_at=DEFAULT_UPDATED_AT,
                evidence_level=DEFAULT_EVIDENCE_LEVEL,
            )
            created += len(batch)
            log.info("  [%s] %d / %d", rel_type, created, total)
        log.info("关系创建完成: %s (%d)", rel_type, total)
