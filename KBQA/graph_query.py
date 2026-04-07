#!/usr/bin/env python3
# coding: utf-8
"""
Neo4j 查询执行器：执行参数化 Cypher 查询并返回结果。
"""
from __future__ import annotations

import logging

from py2neo import Graph

from .config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

log = logging.getLogger("qa")


class GraphQueryExecutor:
    """执行 Cypher 查询的薄封装层。"""

    def __init__(self, uri: str = NEO4J_URI, user: str = NEO4J_USER,
                 password: str = NEO4J_PASSWORD):
        self.graph = Graph(uri, auth=(user, password))
        log.info("Neo4j 连接成功: %s", uri)

    def execute(self, query_groups: list[dict]) -> list[dict]:
        """
        执行 CypherGenerator 输出的查询组。

        输入: [{"question_type": ..., "queries": [{"cypher": ..., "params": ...}]}]
        输出: [{"question_type": ..., "answers": [{...}, ...]}]
        """
        results = []
        for group in query_groups:
            question_type = group["question_type"]
            answers = []
            for q in group["queries"]:
                try:
                    rows = self.graph.run(q["cypher"], **q["params"]).data()
                    answers.extend(rows)
                except Exception as e:
                    log.error("Cypher 执行失败: %s | 参数: %s | 错误: %s",
                              q["cypher"][:80], q["params"], e)
            results.append({
                "question_type": question_type,
                "answers": answers,
            })
        return results
