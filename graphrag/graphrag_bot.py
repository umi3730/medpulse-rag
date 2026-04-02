#!/usr/bin/env python3
# coding: utf-8
"""
GraphRAG 编排器：串联实体抽取 → 归一化 → 子图检索 → 上下文组装 → LLM 生成。
"""
from __future__ import annotations

import logging
import time

from py2neo import Graph

from config import (
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    LLM_MODEL, LLM_BASE_URL,
    LLM_NUM_PREDICT_GENERATION,
    DEFAULT_ANSWER,
    create_llm,
)
from entity_extractor import EntityExtractor
from entity_normalizer import EntityNormalizer
from subgraph_retriever import SubgraphRetriever
from context_builder import ContextBuilder
from generator import GraphRAGGenerator

log = logging.getLogger("graphrag")


class GraphRAGBot:
    """GraphRAG 问答编排器。"""

    def __init__(self, neo4j_uri: str = NEO4J_URI, neo4j_user: str = NEO4J_USER,
                 neo4j_password: str = NEO4J_PASSWORD,
                 llm_model: str = LLM_MODEL, llm_base_url: str = LLM_BASE_URL,
                 debug: bool = False,
                 # 向后兼容
                 ollama_model: str | None = None, ollama_url: str | None = None):
        self.debug = debug
        if ollama_model:
            llm_model = ollama_model
        if ollama_url:
            llm_base_url = ollama_url

        # 共享 LLM 实例
        self.llm = None
        self._llm_available = False
        try:
            self.llm = create_llm(
                model=llm_model,
                base_url=llm_base_url,
                max_tokens=LLM_NUM_PREDICT_GENERATION,
            )
            if self.llm:
                self.llm.invoke("hi")  # 连通测试
                self._llm_available = True
                log.info("GraphRAG LLM (%s) 就绪", llm_model)
            else:
                log.warning("LLM 依赖未安装，GraphRAG 功能受限")
        except Exception as e:
            log.warning("LLM 不可用，GraphRAG 功能受限: %s", e)
            self.llm = None

        # 共享 Neo4j 连接
        self.graph = Graph(neo4j_uri, auth=(neo4j_user, neo4j_password))

        # 管线组件
        self.extractor = EntityExtractor(llm=self.llm)
        self.normalizer = EntityNormalizer()
        self.retriever = SubgraphRetriever(graph=self.graph)
        self.context_builder = ContextBuilder()
        self.generator = GraphRAGGenerator(llm=self.llm)

    @property
    def available(self) -> bool:
        """LLM 是否可用（GraphRAG 核心依赖 LLM）。"""
        return self._llm_available

    # ==================================================================
    # 公共接口
    # ==================================================================
    def chat(self, question: str) -> str:
        """简单接口：返回回答字符串。"""
        return self.chat_detail(question)["answer"]

    def chat_detail(self, question: str) -> dict:
        """
        详细接口：返回回答 + 调试信息 + 图谱数据。

        返回:
          {
            "answer": str,
            "debug": {
              "entities_raw": [...],
              "entities_normalized": {...},
              "subgraph_stats": {...},
              "context_preview": str,
              "context_char_count": int,
              "generation_time_ms": float,
              "model_used": str,
              "total_time_ms": float,
            },
            "graph_data": {"nodes": [...], "edges": [...]},
          }
        """
        t0 = time.time()
        question = question.strip()

        empty_debug = {
            "entities_raw": [], "entities_normalized": {},
            "subgraph_stats": {}, "context_preview": "",
            "context_char_count": 0, "generation_time_ms": 0,
            "model_used": "none", "total_time_ms": 0,
        }
        empty = {
            "answer": DEFAULT_ANSWER,
            "debug": empty_debug,
            "graph_data": {"nodes": [], "edges": []},
        }
        if not question:
            return empty

        # Stage 1: 实体抽取
        raw_entities = self.extractor.extract(question)
        if self.debug and raw_entities:
            log.info("[GraphRAG] 抽取实体: %s", raw_entities)

        if not raw_entities:
            empty["debug"]["total_time_ms"] = round((time.time() - t0) * 1000, 1)
            return empty

        # Stage 2: 实体归一化（复用 KBQA 的 EntityNormalizer）
        normalized = self.normalizer.normalize(raw_entities, has_negation=False)
        entity_dict = normalized["entity_dict"]

        if self.debug:
            log.info("[GraphRAG] 归一化实体: %s", entity_dict)

        if not entity_dict:
            empty["debug"]["entities_raw"] = raw_entities
            empty["debug"]["total_time_ms"] = round((time.time() - t0) * 1000, 1)
            return empty

        # Stage 3: 多跳子图检索
        subgraph = self.retriever.retrieve(entity_dict)
        if self.debug:
            log.info("[GraphRAG] 子图: %d 节点, %d 边, %.0fms",
                     subgraph["stats"]["total_nodes"],
                     subgraph["stats"]["total_edges"],
                     subgraph["stats"]["retrieval_time_ms"])

        # Stage 4: 上下文组装
        context_result = self.context_builder.build(subgraph)
        if self.debug:
            log.info("[GraphRAG] 上下文: %d 字符", context_result["char_count"])

        # Stage 5: LLM 答案生成
        gen_result = self.generator.generate(question, context_result["context_text"])
        if self.debug:
            log.info("[GraphRAG] 生成: %.0fms, 模型: %s",
                     gen_result["generation_time_ms"], gen_result["model_used"])

        answer = gen_result["answer"] or DEFAULT_ANSWER
        total_time = round((time.time() - t0) * 1000, 1)

        # 构建前端可视化数据
        graph_data = self._build_graph_data(subgraph)

        return {
            "answer": answer,
            "debug": {
                "entities_raw": raw_entities,
                "entities_normalized": entity_dict,
                "subgraph_stats": subgraph["stats"],
                "context_preview": context_result["context_preview"],
                "context_char_count": context_result["char_count"],
                "generation_time_ms": gen_result["generation_time_ms"],
                "model_used": gen_result["model_used"],
                "total_time_ms": total_time,
            },
            "graph_data": graph_data,
        }

    @staticmethod
    def _build_graph_data(subgraph: dict) -> dict:
        """将子图转换为前端力导向图格式。"""
        nodes = [{"id": n["name"], "label": n["label"]} for n in subgraph["nodes"]]
        edges = [
            {"source": e["source"], "target": e["target"], "label": e["relationship"]}
            for e in subgraph["edges"]
        ]
        return {"nodes": nodes, "edges": edges}
