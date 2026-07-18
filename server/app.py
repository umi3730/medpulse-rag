#!/usr/bin/env python3
# coding: utf-8
"""
FastAPI 后端：提供问答 API、图谱邻居查询和健康检查。

启动: cd medpulse-rag && python3 -m server.app
"""
from __future__ import annotations

import argparse
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import json

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

# 确保项目根目录在 sys.path 中（用于 KBQA/graphrag 包导入）
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from server.models import (
    ChatRequest, ChatResponse, SessionRenameRequest,
    NeighborResponse, GraphData, GraphNode, GraphEdge, EvidenceItem,
    HealthResponse,
    GraphRAGChatResponse, GraphRAGDebugInfo,
)

log = logging.getLogger("server")

# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_bot = None
_graphrag_bot = None


def _get_bot():
    """获取 ChatBot 单例。"""
    global _bot
    if _bot is None:
        raise RuntimeError("ChatBot 尚未初始化，请等待服务完全启动。")
    return _bot


def _get_graphrag_bot():
    """获取 GraphRAGBot 单例（可能为 None）。"""
    return _graphrag_bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化 ChatBot 和 GraphRAGBot，关闭时释放。"""
    global _bot, _graphrag_bot
    from KBQA.chatbot import ChatBot
    from graphrag.graphrag_bot import GraphRAGBot

    cfg = app.state.bot_config
    _bot = ChatBot(
        neo4j_uri=cfg["neo4j_uri"],
        neo4j_user=cfg["neo4j_user"],
        neo4j_password=cfg["neo4j_password"],
        llm_model=cfg["llm_model"],
        llm_base_url=cfg["llm_base_url"],
        answer_mode=cfg["answer_mode"],
        debug=True,
    )
    log.info("ChatBot 初始化完成")

    try:
        _graphrag_bot = GraphRAGBot(
            neo4j_uri=cfg["neo4j_uri"],
            neo4j_user=cfg["neo4j_user"],
            neo4j_password=cfg["neo4j_password"],
            llm_model=cfg["llm_model"],
            llm_base_url=cfg["llm_base_url"],
            debug=True,
        )
        log.info("GraphRAGBot 初始化完成 (available=%s)", _graphrag_bot.available)
    except Exception as e:
        log.warning("GraphRAGBot 初始化失败: %s", e)
        _graphrag_bot = None

    yield
    _bot = None
    _graphrag_bot = None
    log.info("所有 Bot 已释放")


# ---------------------------------------------------------------------------
# FastAPI 实例
# ---------------------------------------------------------------------------
app = FastAPI(title="医药知识图谱问答 API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """问答接口：返回回答 + 调试信息 + 图谱数据。"""
    bot = _get_bot()
    result = bot.chat_detail(req.question, user_id=req.user_id, session_id=req.session_id)
    return result


@app.post("/api/graphrag/chat", response_model=GraphRAGChatResponse)
async def graphrag_chat(req: ChatRequest):
    """GraphRAG 问答接口：子图检索 + LLM 生成。"""
    bot = _get_graphrag_bot()
    if not bot or not bot.available:
        # 降级到基础问答
        basic = _get_bot()
        result = basic.chat_detail(req.question, user_id=req.user_id, session_id=req.session_id)
        return GraphRAGChatResponse(
            answer=result["answer"],
            mode="fallback_basic",
            debug=GraphRAGDebugInfo(
                entities_normalized=result.get("debug", {}).get("entities", {}),
                subgraph_stats={
                    "total_nodes": len(result.get("graph_data", {}).get("nodes", [])),
                    "total_edges": len(result.get("graph_data", {}).get("edges", [])),
                    "retrieval_time_ms": 0,
                },
                model_used="fallback_basic",
            ),
            graph_data=GraphData(
                nodes=[GraphNode(**n) for n in result["graph_data"]["nodes"]],
                edges=[GraphEdge(**e) for e in result["graph_data"]["edges"]],
            ),
        )
    result = bot.chat_detail(req.question, user_id=req.user_id, session_id=req.session_id)
    return GraphRAGChatResponse(
        answer=result["answer"],
        mode="graphrag",
        debug=GraphRAGDebugInfo(**result["debug"]),
        graph_data=GraphData(
            nodes=[GraphNode(**n) for n in result["graph_data"]["nodes"]],
            edges=[GraphEdge(**e) for e in result["graph_data"]["edges"]],
        ),
        evidence=[EvidenceItem(**item) for item in result.get("evidence", [])],
    )


@app.get("/api/graphrag/memory")
async def graphrag_memory(
    user_id: str = Query("anonymous", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
    session_id: str = Query("default", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
):
    """Return the current local GraphRAG memory snapshot."""
    bot = _get_graphrag_bot()
    if not bot or not getattr(bot, "memory_store", None):
        return {"user_id": user_id, "session_id": session_id, "recent_turns": [], "entities": {}}
    return bot.memory_store.snapshot(user_id=user_id, session_id=session_id)


@app.delete("/api/graphrag/memory")
async def clear_graphrag_memory(
    user_id: str = Query("anonymous", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
    session_id: str = Query("default", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
):
    """Clear the current local GraphRAG memory."""
    bot = _get_graphrag_bot()
    if not bot or not getattr(bot, "memory_store", None):
        return {"turns_deleted": 0, "entities_deleted": 0}
    return bot.memory_store.clear(user_id=user_id, session_id=session_id)


@app.get("/api/graphrag/sessions")
async def graphrag_sessions(
    user_id: str = Query("anonymous", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str = Query("", max_length=100),
):
    """List persisted GraphRAG sessions for one user."""
    bot = _get_graphrag_bot()
    if not bot or not getattr(bot, "memory_store", None):
        return {"user_id": user_id, "sessions": [], "total": 0, "has_more": False, "limit": limit, "offset": offset}
    return {
        "user_id": user_id,
        **bot.memory_store.list_sessions(
            user_id=user_id, limit=limit, offset=offset, query=q,
        ),
    }


@app.get("/api/graphrag/sessions/{session_id}")
async def graphrag_session_history(
    session_id: str,
    user_id: str = Query("anonymous", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
):
    """Return the persisted turns of one user-owned session."""
    if not session_id or len(session_id) > 128 or not all(char.isalnum() or char in "_-" for char in session_id):
        raise HTTPException(status_code=422, detail="Invalid session_id")
    bot = _get_graphrag_bot()
    if not bot or not getattr(bot, "memory_store", None):
        return {"user_id": user_id, "session_id": session_id, "turns": []}
    return {
        "user_id": user_id,
        "session_id": session_id,
        "turns": bot.memory_store.get_session_turns(user_id=user_id, session_id=session_id),
    }


@app.patch("/api/graphrag/sessions/{session_id}")
async def rename_graphrag_session(session_id: str, req: SessionRenameRequest):
    """Rename one user-owned session."""
    if not session_id or len(session_id) > 128 or not all(char.isalnum() or char in "_-" for char in session_id):
        raise HTTPException(status_code=422, detail="Invalid session_id")
    bot = _get_graphrag_bot()
    if not bot or not getattr(bot, "memory_store", None):
        raise HTTPException(status_code=503, detail="GraphRAG memory unavailable")
    try:
        updated = bot.memory_store.rename_session(
            user_id=req.user_id, session_id=session_id, title=req.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"updated": True, "user_id": req.user_id, "session_id": session_id, "title": " ".join(req.title.split())[:80]}


@app.delete("/api/graphrag/sessions/{session_id}")
async def delete_graphrag_session(
    session_id: str,
    user_id: str = Query("anonymous", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
):
    """Delete a user-owned session from SQLite and its semantic memories from Qdrant."""
    if not session_id or len(session_id) > 128 or not all(char.isalnum() or char in "_-" for char in session_id):
        raise HTTPException(status_code=422, detail="Invalid session_id")
    bot = _get_graphrag_bot()
    if not bot or not getattr(bot, "memory_store", None):
        raise HTTPException(status_code=503, detail="GraphRAG memory unavailable")
    vector_store = getattr(bot, "vector_store", None)
    vector_result = {"cleared": False, "available": False}
    if vector_store is not None:
        vector_result = {"available": True, **vector_store.clear(user_id=user_id, session_id=session_id)}
    deleted = bot.memory_store.delete_session(user_id=user_id, session_id=session_id)
    if not deleted["sessions_deleted"]:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True, **deleted, "vector": vector_result}


@app.get("/api/graphrag/vector/stats")
async def graphrag_vector_stats():
    """Return local Qdrant vector store stats."""
    bot = _get_graphrag_bot()
    vector_store = getattr(bot, "vector_store", None) if bot else None
    if not vector_store:
        return {"available": False, "collection": "", "points_count": 0}
    return {"available": True, **vector_store.stats()}


@app.get("/api/graphrag/vector/search")
async def graphrag_vector_search(
    q: str = Query(..., min_length=1),
    limit: int = 5,
    user_id: str = Query("anonymous", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
    session_id: str = Query("default", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
):
    """Search the local Qdrant vector memory."""
    bot = _get_graphrag_bot()
    vector_store = getattr(bot, "vector_store", None) if bot else None
    if not vector_store:
        return {"available": False, "hits": []}
    return {
        "available": True,
        "hits": vector_store.search(
            q,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
        ),
    }


@app.delete("/api/graphrag/vector")
async def clear_graphrag_vector_store(
    user_id: str = Query("anonymous", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
    session_id: str = Query("default", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
):
    """Clear the local Qdrant vector memory collection."""
    bot = _get_graphrag_bot()
    vector_store = getattr(bot, "vector_store", None) if bot else None
    if not vector_store:
        return {"available": False, "cleared": False}
    return {
        "available": True,
        **vector_store.clear(user_id=user_id, session_id=session_id),
    }


def _sse_event(event: str, data: dict) -> str:
    """格式化一个 SSE 事件。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """基础问答流式接口（SSE）。"""
    bot = _get_bot()

    def event_generator():
        for evt in bot.chat_stream(req.question, user_id=req.user_id, session_id=req.session_id):
            yield _sse_event(evt["event"], evt["data"])

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/graphrag/chat/stream")
async def graphrag_chat_stream(req: ChatRequest):
    """GraphRAG 流式问答接口（SSE）。"""
    bot = _get_graphrag_bot()
    if not bot or not bot.available:
        # 降级到基础问答流式
        basic = _get_bot()

        def fallback_generator():
            for evt in basic.chat_stream(req.question, user_id=req.user_id, session_id=req.session_id):
                if evt["event"] == "retrieval":
                    basic_debug = evt["data"].get("debug", {})
                    graph_data = evt["data"].get("graph_data", {"nodes": [], "edges": []})
                    evt["data"] = {
                        "mode": "fallback_basic",
                        "debug": {
                            "entities_raw": [],
                            "entities_normalized": basic_debug.get("entities", {}),
                            "subgraph_stats": {
                                "total_nodes": len(graph_data.get("nodes", [])),
                                "total_edges": len(graph_data.get("edges", [])),
                                "retrieval_time_ms": 0,
                            },
                            "context_preview": "",
                            "context_char_count": 0,
                            "generation_time_ms": 0,
                            "model_used": "fallback_basic",
                            "total_time_ms": 0,
                        },
                        "graph_data": graph_data,
                        "evidence": [],
                    }
                yield _sse_event(evt["event"], evt["data"])

        return StreamingResponse(fallback_generator(), media_type="text/event-stream")

    def event_generator():
        for evt in bot.chat_stream(req.question, user_id=req.user_id, session_id=req.session_id):
            yield _sse_event(evt["event"], evt["data"])

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/graph/neighbors/{name}", response_model=NeighborResponse)
async def graph_neighbors(name: str, limit: int = 50):
    """查询指定节点的所有邻居（用于前端图谱探索）。"""
    bot = _get_bot()
    cypher = (
        "MATCH (n)-[r]-(m) WHERE n.name = $name "
        "RETURN labels(n)[0] AS n_label, n.name AS n_name, "
        "type(r) AS r_type, labels(m)[0] AS m_label, m.name AS m_name "
        "LIMIT $limit"
    )
    try:
        rows = bot.graph_query.graph.run(cypher, name=name, limit=limit).data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    nodes_set: dict[str, str] = {name: "center"}
    edges: list[dict] = []
    for row in rows:
        n_name = row.get("n_name", "")
        m_name = row.get("m_name", "")
        n_label = row.get("n_label", "")
        m_label = row.get("m_label", "")
        r_type = row.get("r_type", "")
        if n_name:
            nodes_set.setdefault(n_name, n_label)
        if m_name:
            nodes_set.setdefault(m_name, m_label)
        if n_name and m_name:
            edges.append({"source": n_name, "target": m_name, "label": r_type})

    # 更新 center 节点的真实标签
    for row in rows:
        if row.get("n_name") == name:
            nodes_set[name] = row.get("n_label", "center")
            break

    graph_data = GraphData(
        nodes=[GraphNode(id=n, label=l) for n, l in nodes_set.items()],
        edges=[GraphEdge(**e) for e in edges],
    )
    return NeighborResponse(center=name, graph_data=graph_data)


@app.get("/api/health", response_model=HealthResponse)
async def health():
    """健康检查：Neo4j 和 Ollama 连通性。"""
    bot = _get_bot()

    neo4j_ok = False
    try:
        bot.graph_query.graph.run("RETURN 1").data()
        neo4j_ok = True
    except Exception:
        pass

    ollama_ok = bot.llm_engine.available
    graphrag_ok = _graphrag_bot is not None and _graphrag_bot.available

    return HealthResponse(
        status="ok" if (neo4j_ok and ollama_ok) else "degraded",
        neo4j=neo4j_ok,
        ollama=ollama_ok,
        graphrag=graphrag_ok,
    )


# ---------------------------------------------------------------------------
# 静态文件（生产模式：前端构建产物）
# ---------------------------------------------------------------------------
_web_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if _web_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="static")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="医药知识图谱问答 API 服务")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--neo4j-uri", default=None)
    parser.add_argument("--neo4j-user", default=None)
    parser.add_argument("--neo4j-password", "--password", default=None)
    parser.add_argument("--llm-provider", default=None, help="LLM 提供商: ollama/openai/anthropic")
    parser.add_argument("--llm-model", default=None, help="LLM 模型名称")
    parser.add_argument("--llm-base-url", default=None, help="LLM API 地址")
    parser.add_argument("--llm-api-key", default=None, help="LLM API Key (商业 API)")
    parser.add_argument("--answer-mode", default="template", choices=["template", "llm"])
    # 向后兼容
    parser.add_argument("--ollama-model", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--ollama-url", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    # 导入 settings 获取默认值
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import settings

    # 如果指定了 provider，覆盖环境变量
    if args.llm_provider:
        import os
        os.environ["LLM_PROVIDER"] = args.llm_provider
    if args.llm_api_key:
        import os
        os.environ["OPENAI_API_KEY"] = args.llm_api_key
        os.environ["ANTHROPIC_API_KEY"] = args.llm_api_key

    # 优先用新参数，兼容旧参数，最后用 settings 默认值
    llm_model = args.llm_model or args.ollama_model or settings.LLM_MODEL
    llm_base_url = args.llm_base_url or args.ollama_url or settings.LLM_BASE_URL

    app.state.bot_config = {
        "neo4j_uri": args.neo4j_uri or settings.NEO4J_URI,
        "neo4j_user": args.neo4j_user or settings.NEO4J_USER,
        "neo4j_password": args.neo4j_password or settings.NEO4J_PASSWORD,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "answer_mode": args.answer_mode,
    }

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
