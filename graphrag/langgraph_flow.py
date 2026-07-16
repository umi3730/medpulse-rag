#!/usr/bin/env python3
# coding: utf-8
"""LangGraph workflow for the medical GraphRAG pipeline."""
from __future__ import annotations

import logging
import time
from typing import Any, TypedDict

from .config import DEFAULT_ANSWER
from .memory_store import DEFAULT_SESSION_ID, DEFAULT_USER_ID, SQLiteMemoryStore
from .vector_store import QdrantVectorStore

try:
    from langgraph.graph import END, StateGraph

    HAS_LANGGRAPH = True
except ImportError:
    END = "__end__"
    StateGraph = None
    HAS_LANGGRAPH = False

log = logging.getLogger("graphrag")


INTENT_RELATIONS: dict[str, list[str]] = {
    "drug": ["common_drug", "recommand_drug", "drugs_of"],
    "food": ["do_eat", "no_eat", "recommand_eat"],
    "check": ["need_check"],
    "symptom": ["has_symptom", "acompany_with"],
    "department": ["belongs_to", "dept_belongs_to"],
}

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "drug": ("药", "用药", "服用", "片", "胶囊", "治疗"),
    "food": ("饮食", "吃", "忌口", "食物", "营养", "水果", "蔬菜"),
    "check": ("检查", "化验", "检测", "筛查", "查什么"),
    "symptom": ("症状", "表现", "并发", "不舒服", "疼", "痛"),
    "department": ("科室", "挂号", "看什么科", "哪个科"),
    "prevent": ("预防", "避免", "注意", "护理"),
}


LIFESTYLE_KEYWORDS = (
    "\u4f5c\u606f", "\u7761\u7720", "\u71ac\u591c", "\u8fd0\u52a8",
    "\u953b\u70bc", "\u751f\u6d3b\u4e60\u60ef", "\u65e5\u5e38",
    "\u751f\u6d3b\u65b9\u5f0f", "\u4f11\u606f", "\u996e\u98df\u4f5c\u606f",
)

def is_lifestyle_question(question: str) -> bool:
    return any(keyword in question for keyword in LIFESTYLE_KEYWORDS)

class GraphRAGState(TypedDict, total=False):
    question: str
    user_id: str
    session_id: str
    started_at: float
    intent: str
    intents: list[str]
    relation_filters: list[str]
    memory_context: str
    memory_entities: dict[str, list[str]]
    memory_turn_count: int
    vector_context: str
    vector_hits: list[dict]
    raw_entities: list[dict]
    entity_dict: dict[str, list[str]]
    subgraph: dict
    context_result: dict
    gen_result: dict
    answer: str
    graph_data: dict
    debug: dict
    error: str
    workflow: str
    retrieval_mode: str


class LangGraphRAGFlow:
    """State-machine orchestration for the existing GraphRAG components."""

    def __init__(
        self,
        *,
        extractor,
        normalizer,
        retriever,
        context_builder,
        generator,
        memory_store: SQLiteMemoryStore | None = None,
        vector_store: QdrantVectorStore | None = None,
        user_id: str = DEFAULT_USER_ID,
        session_id: str = DEFAULT_SESSION_ID,
    ):
        if not HAS_LANGGRAPH or StateGraph is None:
            raise ImportError("langgraph is not installed")

        self.extractor = extractor
        self.normalizer = normalizer
        self.retriever = retriever
        self.context_builder = context_builder
        self.generator = generator
        self.memory_store = memory_store or SQLiteMemoryStore()
        self.vector_store = vector_store
        self.user_id = user_id
        self.session_id = session_id
        self.graph = self._build_graph()

    def run(
        self,
        question: str,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict:
        question = question.strip()
        initial: GraphRAGState = {
            "question": question,
            "user_id": user_id or self.user_id,
            "session_id": session_id or self.session_id,
            "started_at": time.time(),
            "workflow": "langgraph",
        }
        if not question:
            return self._empty_result(0)

        try:
            state = self.graph.invoke(initial)
        except Exception as exc:
            log.exception("LangGraph GraphRAG workflow failed: %s", exc)
            elapsed = round((time.time() - initial["started_at"]) * 1000, 1)
            return self._empty_result(elapsed, error=str(exc))

        total_time = round((time.time() - initial["started_at"]) * 1000, 1)
        return self._to_response(state, total_time)

    def _build_graph(self):
        graph = StateGraph(GraphRAGState)
        graph.add_node("load_memory", self._load_memory)
        graph.add_node("classify_intent", self._classify_intent)
        graph.add_node("extract_entities", self._extract_entities)
        graph.add_node("normalize_entities", self._normalize_entities)
        graph.add_node("retrieve_subgraph", self._retrieve_subgraph)
        graph.add_node("build_context", self._build_context)
        graph.add_node("generate_answer", self._generate_answer)
        graph.add_node("update_memory", self._update_memory)
        graph.add_node("fallback_answer", self._fallback_answer)

        graph.set_entry_point("load_memory")
        graph.add_edge("load_memory", "classify_intent")
        graph.add_edge("classify_intent", "extract_entities")
        graph.add_conditional_edges(
            "extract_entities",
            self._has_entities,
            {"continue": "normalize_entities", "fallback": "fallback_answer"},
        )
        graph.add_conditional_edges(
            "normalize_entities",
            self._has_entity_dict,
            {"continue": "retrieve_subgraph", "fallback": "fallback_answer"},
        )
        graph.add_edge("retrieve_subgraph", "build_context")
        graph.add_conditional_edges(
            "build_context",
            self._has_context,
            {"continue": "generate_answer", "fallback": "fallback_answer"},
        )
        graph.add_edge("generate_answer", "update_memory")
        graph.add_edge("fallback_answer", "update_memory")
        graph.add_edge("update_memory", END)
        return graph.compile()

    def _load_memory(self, state: GraphRAGState) -> GraphRAGState:
        user_id = state.get("user_id", self.user_id)
        session_id = state.get("session_id", self.session_id)
        memory = self.memory_store.build_context(user_id=user_id, session_id=session_id)
        vector = {"context_text": "", "hits": []}
        if self.vector_store is not None:
            try:
                min_score = 0.36 if is_lifestyle_question(state["question"]) else 0.30
                vector = self.vector_store.build_context(
                    state["question"],
                    user_id=user_id,
                    session_id=session_id,
                    min_score=min_score,
                )
            except Exception as exc:
                log.warning("Failed to load Qdrant vector memory: %s", exc)
        state["memory_context"] = memory.get("context_text", "")
        state["memory_entities"] = memory.get("entities", {})
        state["memory_turn_count"] = len(memory.get("recent_turns", []))
        state["vector_context"] = vector.get("context_text", "")
        state["vector_hits"] = vector.get("hits", [])
        return state

    def _classify_intent(self, state: GraphRAGState) -> GraphRAGState:
        question = state["question"]
        intents = [
            intent
            for intent, keywords in INTENT_KEYWORDS.items()
            if any(keyword in question for keyword in keywords)
        ]
        if is_lifestyle_question(question) and "lifestyle" not in intents:
            intents.append("lifestyle")
        if not intents:
            intents = ["general"]

        relation_filters: list[str] = []
        for intent in intents:
            for rel in INTENT_RELATIONS.get(intent, []):
                if rel not in relation_filters:
                    relation_filters.append(rel)

        state["intents"] = intents
        state["intent"] = "+".join(intents)
        state["relation_filters"] = relation_filters
        return state

    def _extract_entities(self, state: GraphRAGState) -> GraphRAGState:
        raw_entities = self.extractor.extract(state["question"]) or []
        if not raw_entities:
            raw_entities = self._entities_to_raw(state.get("memory_entities", {}))
            if raw_entities:
                state["retrieval_mode"] = "memory_entity_reuse"
        state["raw_entities"] = raw_entities
        return state

    def _normalize_entities(self, state: GraphRAGState) -> GraphRAGState:
        normalized = self.normalizer.normalize(state.get("raw_entities", []), has_negation=False)
        state["entity_dict"] = normalized.get("entity_dict", {})
        return state

    def _retrieve_subgraph(self, state: GraphRAGState) -> GraphRAGState:
        if "lifestyle" in state.get("intents", []):
            state["subgraph"] = {
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
            state["retrieval_mode"] = "lifestyle_memory"
            return state

        relation_filters = state.get("relation_filters") or None
        subgraph = self.retriever.retrieve(state.get("entity_dict", {}), relation_filters=relation_filters)
        retrieval_mode = "intent_filtered" if relation_filters else "broad"

        if relation_filters and not subgraph.get("edges"):
            subgraph = self.retriever.retrieve(state.get("entity_dict", {}))
            retrieval_mode = "fallback_broad"

        state["subgraph"] = subgraph
        state["retrieval_mode"] = retrieval_mode
        return state

    def _build_context(self, state: GraphRAGState) -> GraphRAGState:
        context_result = self.context_builder.build(state.get("subgraph", {}))
        memory_context = state.get("memory_context", "")
        vector_context = state.get("vector_context", "")
        extra_contexts = []
        if memory_context:
            extra_contexts.append(f"[Conversation Memory]\n{memory_context}")
        if vector_context:
            extra_contexts.append(f"[Qdrant Vector Memory]\n{vector_context}")
        if extra_contexts:
            context_text = context_result.get("context_text", "")
            extra_text = "\n\n".join(extra_contexts)
            merged_context = (
                f"{context_text}\n\n{extra_text}"
                if context_text
                else extra_text
            )
            context_result = {
                **context_result,
                "context_text": merged_context,
                "context_preview": merged_context[:500],
                "char_count": len(merged_context),
            }
        state["context_result"] = context_result
        return state

    def _generate_answer(self, state: GraphRAGState) -> GraphRAGState:
        context = state.get("context_result", {}).get("context_text", "")
        gen_result = self.generator.generate(state["question"], context)
        state["gen_result"] = gen_result
        state["answer"] = gen_result.get("answer") or DEFAULT_ANSWER
        return state

    def _fallback_answer(self, state: GraphRAGState) -> GraphRAGState:
        state["answer"] = DEFAULT_ANSWER
        state.setdefault("gen_result", {"answer": "", "generation_time_ms": 0, "model_used": "none"})
        state.setdefault("context_result", {"context_preview": "", "char_count": 0})
        state.setdefault("subgraph", {"nodes": [], "edges": [], "stats": {}})
        return state

    def _update_memory(self, state: GraphRAGState) -> GraphRAGState:
        try:
            self.memory_store.add_turn(
                question=state.get("question", ""),
                answer=state.get("answer", ""),
                intents=state.get("intents", []),
                entities=state.get("entity_dict", {}),
                user_id=state.get("user_id", self.user_id),
                session_id=state.get("session_id", self.session_id),
            )
            if self.vector_store is not None:
                self.vector_store.add_memory_turn(
                    question=state.get("question", ""),
                    answer=state.get("answer", ""),
                    intents=state.get("intents", []),
                    entities=state.get("entity_dict", {}),
                    user_id=state.get("user_id", self.user_id),
                    session_id=state.get("session_id", self.session_id),
                )
        except Exception as exc:
            log.warning("Failed to update GraphRAG memory: %s", exc)
            state["error"] = str(exc)
        return state

    @staticmethod
    def _has_entities(state: GraphRAGState) -> str:
        return "continue" if state.get("raw_entities") else "fallback"

    @staticmethod
    def _has_entity_dict(state: GraphRAGState) -> str:
        return "continue" if state.get("entity_dict") else "fallback"

    @staticmethod
    def _has_context(state: GraphRAGState) -> str:
        return "continue" if state.get("context_result", {}).get("context_text") else "fallback"

    def _to_response(self, state: GraphRAGState, total_time_ms: float) -> dict:
        subgraph = state.get("subgraph", {"nodes": [], "edges": [], "stats": {}})
        context_result = state.get("context_result", {"context_preview": "", "char_count": 0})
        gen_result = state.get("gen_result", {"generation_time_ms": 0, "model_used": "none"})

        return {
            "answer": state.get("answer") or DEFAULT_ANSWER,
            "debug": {
                "workflow": "langgraph",
                "intent": state.get("intent", "general"),
                "intents": state.get("intents", []),
                "relation_filters": state.get("relation_filters", []),
                "retrieval_mode": state.get("retrieval_mode", "none"),
                "memory_turn_count": state.get("memory_turn_count", 0),
                "memory_context_preview": state.get("memory_context", "")[:500],
                "memory_entities": state.get("memory_entities", {}),
                "vector_hit_count": len(state.get("vector_hits", [])),
                "vector_context_preview": state.get("vector_context", "")[:500],
                "entities_raw": state.get("raw_entities", []),
                "entities_normalized": state.get("entity_dict", {}),
                "subgraph_stats": subgraph.get("stats", {}),
                "context_preview": context_result.get("context_preview", ""),
                "context_char_count": context_result.get("char_count", 0),
                "generation_time_ms": gen_result.get("generation_time_ms", 0),
                "model_used": gen_result.get("model_used", "none"),
                "total_time_ms": total_time_ms,
                "error": state.get("error", ""),
            },
            "graph_data": self._build_graph_data(subgraph),
        }

    def _empty_result(self, total_time_ms: float, error: str = "") -> dict:
        return {
            "answer": DEFAULT_ANSWER,
            "debug": {
                "workflow": "langgraph",
                "intent": "none",
                "intents": [],
                "relation_filters": [],
                "retrieval_mode": "none",
                "memory_turn_count": 0,
                "memory_context_preview": "",
                "memory_entities": {},
                "vector_hit_count": 0,
                "vector_context_preview": "",
                "entities_raw": [],
                "entities_normalized": {},
                "subgraph_stats": {},
                "context_preview": "",
                "context_char_count": 0,
                "generation_time_ms": 0,
                "model_used": "none",
                "total_time_ms": total_time_ms,
                "error": error,
            },
            "graph_data": {"nodes": [], "edges": []},
        }

    @staticmethod
    def _build_graph_data(subgraph: dict[str, Any]) -> dict:
        nodes = [{"id": n["name"], "label": n["label"]} for n in subgraph.get("nodes", [])]
        edges = [
            {"source": e["source"], "target": e["target"], "label": e["relationship"]}
            for e in subgraph.get("edges", [])
        ]
        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _entities_to_raw(entities: dict[str, list[str]]) -> list[dict]:
        raw_entities: list[dict] = []
        for entity_type, names in entities.items():
            for name in names:
                raw_entities.append({"name": name, "type": entity_type})
                if len(raw_entities) >= 6:
                    return raw_entities
        return raw_entities
