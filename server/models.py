#!/usr/bin/env python3
# coding: utf-8
"""Pydantic 请求/响应模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---- 请求 ----
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="用户问题")
    user_id: str = Field(
        "anonymous",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="稳定用户标识；未登录版本由浏览器生成",
    )
    session_id: str = Field(
        "default",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="当前对话会话标识",
    )


# ---- 响应子模型 ----
class CypherQuery(BaseModel):
    cypher: str
    params: dict


class DebugInfo(BaseModel):
    level: int = Field(0, description="降级等级: 1=全LLM, 2=LLM实体+关键词, 3=词典NER")
    intents: list[str] = []
    entities: dict[str, list[str]] = {}
    cypher_queries: list[CypherQuery] = []
    result_count: int = 0


class GraphNode(BaseModel):
    id: str
    label: str


class GraphEdge(BaseModel):
    source: str
    target: str
    label: str


class GraphData(BaseModel):
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []


class EvidenceItem(BaseModel):
    id: str
    kind: str
    subject: str
    predicate: str
    object: str
    source_name: str = "寻医问药网历史数据集"
    source_url: str = ""
    updated_at: str = "unknown"
    evidence_level: str = "legacy_unverified"


class ChatResponse(BaseModel):
    answer: str
    debug: DebugInfo
    graph_data: GraphData


# ---- 邻居查询 ----
class NeighborResponse(BaseModel):
    center: str
    graph_data: GraphData


# ---- GraphRAG 响应 ----
class GraphRAGDebugInfo(BaseModel):
    workflow: str = "legacy"
    intent: str = "general"
    intents: list[str] = []
    query_plan: dict = {}
    requested_fields: list[str] = []
    relation_filters: list[str] = []
    detail_level: str = "standard"
    needs_clarification: bool = False
    risk_level: str = "low"
    retrieval_mode: str = "none"
    memory_turn_count: int = 0
    memory_scope: str = "conversation_only"
    evidence_scope: str = "neo4j_subgraph"
    evidence_count: int = 0
    memory_context_preview: str = ""
    memory_entities: dict[str, list[str]] = {}
    vector_hit_count: int = 0
    embedding_provider: str = "none"
    embedding_model: str = "none"
    embedding_dimension: int = 0
    embedding_fallback_reason: str = ""
    vector_context_preview: str = ""
    entities_raw: list[dict] = []
    entities_normalized: dict[str, list[str]] = {}
    subgraph_stats: dict = {}
    context_preview: str = ""
    context_char_count: int = 0
    generation_time_ms: float = 0
    model_used: str = "none"
    total_time_ms: float = 0
    error: str = ""


class GraphRAGChatResponse(BaseModel):
    answer: str
    mode: str = "graphrag"
    debug: GraphRAGDebugInfo
    graph_data: GraphData
    evidence: list[EvidenceItem] = []


# ---- 健康检查 ----
class HealthResponse(BaseModel):
    status: str
    neo4j: bool
    ollama: bool
    graphrag: bool = False
