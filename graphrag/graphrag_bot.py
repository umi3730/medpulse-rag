#!/usr/bin/env python3
# coding: utf-8
"""
GraphRAG 编排器：串联实体抽取 → 归一化 → 子图检索 → 上下文组装 → LLM 生成。
"""
from __future__ import annotations

import logging
import time

from neo4j_client import Neo4jGraph as Graph

from .config import (
    NEO4J_URI, NEO4J_USER, NEO4J_DATABASE, NEO4J_PASSWORD,
    LLM_MODEL, LLM_BASE_URL,
    LLM_NUM_PREDICT_GENERATION,
    DEFAULT_ANSWER,
    create_llm,
)
from .entity_extractor import EntityExtractor
from KBQA.entity_normalizer import EntityNormalizer
from .subgraph_retriever import SubgraphRetriever
from .context_builder import ContextBuilder
from .generator import GraphRAGGenerator, build_safe_fallback_answer
from .memory_store import DEFAULT_SESSION_ID, DEFAULT_USER_ID, SQLiteMemoryStore
from .question_planner import QuestionPlanner
from .vector_store import QdrantVectorStore

try:
    from .langgraph_flow import INTENT_KEYWORDS, INTENT_RELATIONS, LangGraphRAGFlow, is_lifestyle_question
except ImportError:
    INTENT_KEYWORDS = {}
    INTENT_RELATIONS = {}
    LangGraphRAGFlow = None

    def is_lifestyle_question(question: str) -> bool:
        return False

log = logging.getLogger("graphrag")


class GraphRAGBot:
    """GraphRAG 问答编排器。"""

    def __init__(self, neo4j_uri: str = NEO4J_URI, neo4j_user: str = NEO4J_USER,
                 neo4j_password: str = NEO4J_PASSWORD,
                 neo4j_database: str = NEO4J_DATABASE,
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
        self.graph = Graph(neo4j_uri, auth=(neo4j_user, neo4j_password), name=neo4j_database)

        # 管线组件
        self.extractor = EntityExtractor(llm=self.llm)
        self.normalizer = EntityNormalizer()
        self.retriever = SubgraphRetriever(graph=self.graph)
        self.context_builder = ContextBuilder()
        self.generator = GraphRAGGenerator(llm=self.llm)
        self.planner = QuestionPlanner()
        self.memory_store = SQLiteMemoryStore()
        self.vector_store = None
        try:
            self.vector_store = QdrantVectorStore()
            log.info("GraphRAG Qdrant vector store enabled")
        except Exception as e:
            log.warning("GraphRAG Qdrant vector store unavailable: %s", e)
        self.user_id = DEFAULT_USER_ID
        self.session_id = DEFAULT_SESSION_ID
        self.flow = None
        if LangGraphRAGFlow is not None:
            try:
                self.flow = LangGraphRAGFlow(
                    extractor=self.extractor,
                    normalizer=self.normalizer,
                    retriever=self.retriever,
                    context_builder=self.context_builder,
                    generator=self.generator,
                    memory_store=self.memory_store,
                    vector_store=self.vector_store,
                    user_id=self.user_id,
                    session_id=self.session_id,
                )
                log.info("GraphRAG LangGraph workflow enabled")
            except Exception as e:
                log.warning("GraphRAG LangGraph workflow unavailable: %s", e)

    @property
    def available(self) -> bool:
        """LLM 是否可用（GraphRAG 核心依赖 LLM）。"""
        return self._llm_available

    # ==================================================================
    # 公共接口
    # ==================================================================
    def chat(
        self,
        question: str,
        *,
        user_id: str = DEFAULT_USER_ID,
        session_id: str = DEFAULT_SESSION_ID,
    ) -> str:
        """简单接口：返回回答字符串。"""
        return self.chat_detail(question, user_id=user_id, session_id=session_id)["answer"]

    def chat_detail(
        self,
        question: str,
        *,
        user_id: str = DEFAULT_USER_ID,
        session_id: str = DEFAULT_SESSION_ID,
    ) -> dict:
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
            "evidence": [],
        }
        if not question:
            return empty

        if self.flow is not None:
            return self.flow.run(question, user_id=user_id, session_id=session_id)

        memory = self.memory_store.build_context(user_id=user_id, session_id=session_id)
        memory_context = memory.get("context_text", "")
        memory_entities = memory.get("entities", {})
        memory_turn_count = len(memory.get("recent_turns", []))
        plan = self.planner.plan(
            question, has_memory_entities=bool(memory_entities)
        ).to_dict()
        if plan["needs_clarification"]:
            answer = "请先告诉我你指的是哪一种疾病或症状，我再针对它回答。"
            return {
                "answer": answer,
                "debug": {
                    **empty_debug,
                    "workflow": "legacy",
                    "intent": plan["intent"],
                    "intents": plan["intents"],
                    "query_plan": plan,
                    "requested_fields": plan["requested_fields"],
                    "relation_filters": plan["relation_filters"],
                    "detail_level": plan["detail_level"],
                    "needs_clarification": True,
                    "risk_level": plan["risk_level"],
                    "retrieval_mode": "clarification",
                    "memory_turn_count": memory_turn_count,
                    "memory_scope": "conversation_only",
                    "evidence_scope": "neo4j_subgraph",
                    "evidence_count": 0,
                    "memory_context_preview": memory_context[:500],
                    "memory_entities": memory_entities,
                    **self._embedding_debug(),
                },
                "graph_data": {"nodes": [], "edges": []},
                "evidence": [],
            }
        vector_context = ""
        vector_hits = []
        if self.vector_store is not None:
            try:
                min_score = 0.36 if is_lifestyle_question(question) else 0.30
                vector = self.vector_store.build_context(
                    question,
                    user_id=user_id,
                    session_id=session_id,
                    min_score=min_score,
                )
                vector_context = vector.get("context_text", "")
                vector_hits = vector.get("hits", [])
            except Exception as e:
                log.warning("GraphRAG vector memory load failed: %s", e)

        # Stage 1: 实体抽取
        raw_entities = self.extractor.extract(question)
        if self.debug and raw_entities:
            log.info("[GraphRAG] 抽取实体: %s", raw_entities)

        if not raw_entities:
            raw_entities = self._entities_to_raw(memory_entities)
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
        relation_filters = plan["relation_filters"]
        if is_lifestyle_question(question) and not plan["requested_fields"]:
            subgraph = self._empty_subgraph()
            retrieval_mode = "lifestyle_memory"
        else:
            subgraph = self.retriever.retrieve(
                entity_dict,
                relation_filters=relation_filters,
                property_filters=plan["requested_fields"],
                include_neighbors=bool(relation_filters),
            )
            retrieval_mode = "intent_filtered" if relation_filters else "property_filtered"
        if self.debug:
            log.info("[GraphRAG] 子图: %d 节点, %d 边, %.0fms",
                     subgraph["stats"]["total_nodes"],
                     subgraph["stats"]["total_edges"],
                     subgraph["stats"]["retrieval_time_ms"])

        # Stage 4: 上下文组装
        context_result = self.context_builder.build(subgraph)
        conversation_parts = []
        if memory_context:
            conversation_parts.append(memory_context)
        if vector_context:
            conversation_parts.append(vector_context)
        conversation_context = "\n\n".join(conversation_parts)
        if self.debug:
            log.info("[GraphRAG] 上下文: %d 字符", context_result["char_count"])

        # Stage 5: LLM 答案生成
        gen_result = self.generator.generate(
            question,
            context_result["context_text"],
            query_plan=plan,
            conversation_context=conversation_context,
        )
        if self.debug:
            log.info("[GraphRAG] 生成: %.0fms, 模型: %s",
                     gen_result["generation_time_ms"], gen_result["model_used"])

        answer = gen_result["answer"] or build_safe_fallback_answer(question, plan)
        total_time = round((time.time() - t0) * 1000, 1)

        try:
            self.memory_store.add_turn(
                question=question,
                answer=answer,
                intents=plan["intents"],
                entities=entity_dict,
                user_id=user_id,
                session_id=session_id,
            )
            if self.vector_store is not None:
                self.vector_store.add_memory_turn(
                    question=question,
                    answer=answer,
                    intents=plan["intents"],
                    entities=entity_dict,
                    user_id=user_id,
                    session_id=session_id,
                )
        except Exception as e:
            log.warning("GraphRAG memory update failed: %s", e)

        # 构建前端可视化数据
        graph_data = self._build_graph_data(subgraph)

        return {
            "answer": answer,
            "debug": {
                "entities_raw": raw_entities,
                "entities_normalized": entity_dict,
                "subgraph_stats": subgraph["stats"],
                "workflow": "legacy",
                "intent": plan["intent"],
                "intents": plan["intents"],
                "query_plan": plan,
                "requested_fields": plan["requested_fields"],
                "relation_filters": relation_filters,
                "detail_level": plan["detail_level"],
                "needs_clarification": plan["needs_clarification"],
                "risk_level": plan["risk_level"],
                "retrieval_mode": retrieval_mode,
                "memory_turn_count": memory_turn_count,
                "memory_scope": "conversation_only",
                "evidence_scope": "neo4j_subgraph",
                "evidence_count": len(context_result.get("evidence_items", [])),
                "memory_context_preview": memory_context[:500],
                "memory_entities": memory_entities,
                "vector_hit_count": len(vector_hits),
                **self._embedding_debug(),
                "vector_context_preview": vector_context[:500],
                "context_preview": context_result["context_preview"],
                "context_char_count": context_result["char_count"],
                "generation_time_ms": gen_result["generation_time_ms"],
                "model_used": gen_result["model_used"],
                "total_time_ms": total_time,
            },
            "graph_data": graph_data,
            "evidence": context_result.get("evidence_items", []),
        }

    def chat_stream(
        self,
        question: str,
        *,
        user_id: str = DEFAULT_USER_ID,
        session_id: str = DEFAULT_SESSION_ID,
    ):
        """
        流式问答接口，yield SSE 事件 dict：
          {"event": "retrieval", "data": {debug, graph_data, mode}}
          {"event": "delta",     "data": {"chunk": str}}
          {"event": "done",      "data": {"answer": str, "total_time_ms": float}}
        """
        import json as _json

        t0 = time.time()
        question = question.strip()
        if not question:
            return

        memory = self.memory_store.build_context(user_id=user_id, session_id=session_id)
        memory_context = memory.get("context_text", "")
        memory_entities = memory.get("entities", {})
        memory_turn_count = len(memory.get("recent_turns", []))
        plan = self.planner.plan(
            question, has_memory_entities=bool(memory_entities)
        ).to_dict()
        if plan["needs_clarification"]:
            answer = "请先告诉我你指的是哪一种疾病或症状，我再针对它回答。"
            debug_info = {
                "entities_raw": [],
                "entities_normalized": {},
                "subgraph_stats": {},
                "workflow": "legacy_stream",
                "intent": plan["intent"],
                "intents": plan["intents"],
                "query_plan": plan,
                "requested_fields": plan["requested_fields"],
                "relation_filters": plan["relation_filters"],
                "detail_level": plan["detail_level"],
                "needs_clarification": True,
                "risk_level": plan["risk_level"],
                "retrieval_mode": "clarification",
                "memory_turn_count": memory_turn_count,
                "memory_scope": "conversation_only",
                "evidence_scope": "neo4j_subgraph",
                "evidence_count": 0,
                "memory_context_preview": memory_context[:500],
                "memory_entities": memory_entities,
                "vector_hit_count": 0,
                **self._embedding_debug(),
                "vector_context_preview": "",
                "context_preview": "",
                "context_char_count": 0,
                "generation_time_ms": 0,
                "model_used": "none",
                "total_time_ms": round((time.time() - t0) * 1000, 1),
            }
            yield {
                "event": "retrieval",
                "data": {
                    "debug": debug_info,
                    "graph_data": {"nodes": [], "edges": []},
                    "evidence": [],
                    "mode": "graphrag",
                },
            }
            yield {"event": "delta", "data": {"chunk": answer}}
            yield {
                "event": "done",
                "data": {"answer": answer, "total_time_ms": debug_info["total_time_ms"]},
            }
            return
        vector_context = ""
        vector_hits = []
        if self.vector_store is not None:
            try:
                min_score = 0.36 if is_lifestyle_question(question) else 0.30
                vector = self.vector_store.build_context(
                    question,
                    user_id=user_id,
                    session_id=session_id,
                    min_score=min_score,
                )
                vector_context = vector.get("context_text", "")
                vector_hits = vector.get("hits", [])
            except Exception as e:
                log.warning("GraphRAG vector memory load failed: %s", e)

        # Stage 1: 实体抽取
        raw_entities = self.extractor.extract(question)
        if not raw_entities:
            raw_entities = self._entities_to_raw(memory_entities)
            if not raw_entities:
                yield {"event": "done", "data": {
                    "answer": build_safe_fallback_answer(question, plan),
                    "total_time_ms": 0,
                }}
                return

        # Stage 2: 实体归一化
        normalized = self.normalizer.normalize(raw_entities, has_negation=False)
        entity_dict = normalized["entity_dict"]
        if not entity_dict:
            yield {"event": "done", "data": {
                "answer": build_safe_fallback_answer(question, plan),
                "total_time_ms": 0,
            }}
            return

        # Stage 3: 多跳子图检索
        relation_filters = plan["relation_filters"]
        if is_lifestyle_question(question) and not plan["requested_fields"]:
            subgraph = self._empty_subgraph()
            retrieval_mode = "lifestyle_memory"
        else:
            subgraph = self.retriever.retrieve(
                entity_dict,
                relation_filters=relation_filters,
                property_filters=plan["requested_fields"],
                include_neighbors=bool(relation_filters),
            )
            retrieval_mode = "intent_filtered" if relation_filters else "property_filtered"

        # Stage 4: 上下文组装
        context_result = self.context_builder.build(subgraph)
        conversation_parts = []
        if memory_context:
            conversation_parts.append(memory_context)
        if vector_context:
            conversation_parts.append(vector_context)
        conversation_context = "\n\n".join(conversation_parts)

        # 构建图谱可视化数据
        graph_data = self._build_graph_data(subgraph)

        # yield retrieval 事件（检索完成，立即推送 debug + 图谱）
        debug_info = {
            "entities_raw": raw_entities,
            "entities_normalized": entity_dict,
            "subgraph_stats": subgraph["stats"],
            "workflow": "legacy_stream",
            "intent": plan["intent"],
            "intents": plan["intents"],
            "query_plan": plan,
            "requested_fields": plan["requested_fields"],
            "relation_filters": relation_filters,
            "detail_level": plan["detail_level"],
            "needs_clarification": plan["needs_clarification"],
            "risk_level": plan["risk_level"],
            "retrieval_mode": retrieval_mode,
            "memory_turn_count": memory_turn_count,
            "memory_scope": "conversation_only",
            "evidence_scope": "neo4j_subgraph",
            "evidence_count": len(context_result.get("evidence_items", [])),
            "memory_context_preview": memory_context[:500],
            "memory_entities": memory_entities,
            "vector_hit_count": len(vector_hits),
            **self._embedding_debug(),
            "vector_context_preview": vector_context[:500],
            "context_preview": context_result["context_preview"],
            "context_char_count": context_result["char_count"],
            "generation_time_ms": 0,
            "model_used": "pending",
            "total_time_ms": 0,
        }
        yield {
            "event": "retrieval",
            "data": {
                "debug": debug_info,
                "graph_data": graph_data,
                "evidence": context_result.get("evidence_items", []),
                "mode": "graphrag",
            },
        }

        # Stage 5: 流式 LLM 生成
        full_answer = ""
        for chunk in self.generator.stream(
            question,
            context_result["context_text"],
            query_plan=plan,
            conversation_context=conversation_context,
        ):
            if isinstance(chunk, dict):
                # 生成结束的元数据
                break
            full_answer += chunk
            yield {"event": "delta", "data": {"chunk": chunk}}

        if not full_answer:
            full_answer = build_safe_fallback_answer(question, plan)

        try:
            self.memory_store.add_turn(
                question=question,
                answer=full_answer,
                intents=plan["intents"],
                entities=entity_dict,
                user_id=user_id,
                session_id=session_id,
            )
            if self.vector_store is not None:
                self.vector_store.add_memory_turn(
                    question=question,
                    answer=full_answer,
                    intents=plan["intents"],
                    entities=entity_dict,
                    user_id=user_id,
                    session_id=session_id,
                )
        except Exception as e:
            log.warning("GraphRAG memory update failed: %s", e)

        total_time = round((time.time() - t0) * 1000, 1)
        yield {"event": "done", "data": {"answer": full_answer, "total_time_ms": total_time}}

    @staticmethod
    def _empty_subgraph() -> dict:
        return {
            "entities_found": [],
            "nodes": [],
            "edges": [],
            "stats": {
                "total_nodes": 0,
                "total_edges": 0,
                "retrieval_time_ms": 0,
                "relation_filters": [],
            },
        }

    def _embedding_debug(self) -> dict:
        provider = getattr(self.vector_store, "embedding_provider", None)
        return {
            "embedding_provider": getattr(provider, "name", "none"),
            "embedding_model": getattr(provider, "model_name", "none"),
            "embedding_dimension": getattr(provider, "dimension", 0),
            "embedding_fallback_reason": getattr(
                self.vector_store, "embedding_fallback_reason", ""
            ),
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

    @staticmethod
    def _classify_relation_filters(question: str) -> list[str]:
        """Infer relation filters without requiring LangGraph at runtime."""
        filters: list[str] = []
        if not INTENT_KEYWORDS or not INTENT_RELATIONS:
            return filters

        for intent, keywords in INTENT_KEYWORDS.items():
            if any(keyword in question for keyword in keywords):
                for rel in INTENT_RELATIONS.get(intent, []):
                    if rel not in filters:
                        filters.append(rel)
        return filters

    @staticmethod
    def _entities_to_raw(entities: dict[str, list[str]]) -> list[dict]:
        raw_entities: list[dict] = []
        for entity_type, names in entities.items():
            for name in names:
                raw_entities.append({"name": name, "type": entity_type})
                if len(raw_entities) >= 6:
                    return raw_entities
        return raw_entities
