#!/usr/bin/env python3
# coding: utf-8
"""
FastAPI 后端：提供问答 API、图谱邻居查询和健康检查。

启动: cd MedicalGraphRAGSystem && python3 -m server.app
"""
from __future__ import annotations

import argparse
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 把 qa_system 加入 sys.path（py2neo 等模块在其下）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "qa_system"))

from server.models import (
    ChatRequest, ChatResponse,
    NeighborResponse, GraphData, GraphNode, GraphEdge,
    HealthResponse,
)

log = logging.getLogger("server")

# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_bot = None


def _get_bot():
    """获取 ChatBot 单例。"""
    global _bot
    if _bot is None:
        raise RuntimeError("ChatBot 尚未初始化，请等待服务完全启动。")
    return _bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化 ChatBot，关闭时释放。"""
    global _bot
    from chatbot import ChatBot
    cfg = app.state.bot_config
    _bot = ChatBot(
        neo4j_uri=cfg["neo4j_uri"],
        neo4j_user=cfg["neo4j_user"],
        neo4j_password=cfg["neo4j_password"],
        ollama_model=cfg["ollama_model"],
        ollama_url=cfg["ollama_url"],
        answer_mode=cfg["answer_mode"],
        debug=True,
    )
    log.info("ChatBot 初始化完成")
    yield
    _bot = None
    log.info("ChatBot 已释放")


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
    result = bot.chat_detail(req.question)
    return result


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

    return HealthResponse(
        status="ok" if (neo4j_ok and ollama_ok) else "degraded",
        neo4j=neo4j_ok,
        ollama=ollama_ok,
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
    parser.add_argument("--neo4j-uri", default="bolt://127.0.0.1:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="neo4j")
    parser.add_argument("--ollama-model", default="qwen3:8b")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--answer-mode", default="template", choices=["template", "llm"])
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    app.state.bot_config = {
        "neo4j_uri": args.neo4j_uri,
        "neo4j_user": args.neo4j_user,
        "neo4j_password": args.neo4j_password,
        "ollama_model": args.ollama_model,
        "ollama_url": args.ollama_url,
        "answer_mode": args.answer_mode,
    }

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
